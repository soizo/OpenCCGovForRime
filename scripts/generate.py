"""Generate isolated OpenCC data and small Rime schema overlays."""

import argparse
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import yaml

PREFIX = "govrime_"


def compile_opencc(source: Path, target: Path) -> None:
    """Lower the non-jieba upstream configs to the classic Rime OpenCC format."""
    target.mkdir(parents=True, exist_ok=False)
    compiled = set()

    def dictionary(node):
        if not isinstance(node, dict):
            raise TypeError("Invalid OpenCC dictionary")
        if node.get("type") == "group":
            if (
                set(node) - {"type", "dicts", "match_policy"}
                or node.get("match_policy", "short_circuit") != "short_circuit"
            ):
                raise ValueError("Unsupported OpenCC group policy")
            return {
                "type": "group",
                "dicts": [dictionary(child) for child in node["dicts"]],
            }
        if set(node) != {"type", "file"} or node["type"] != "text":
            raise ValueError("Expected an upstream text dictionary")
        name = node["file"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+\.txt", name):
            raise ValueError(f"Unsafe dictionary path: {name}")
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symlink dictionary: {name}")
        output = PREFIX + Path(name).stem + ".ocd2"
        if name not in compiled:
            subprocess.run(
                [
                    "opencc_dict",
                    "-i",
                    str(path),
                    "-o",
                    str(target / output),
                    "-f",
                    "text",
                    "-t",
                    "ocd2",
                ],
                check=True,
            )
            compiled.add(name)
        return {"type": "ocd2", "file": output}

    for name in ("t2gov_keep_simp", "s2t"):
        try:
            config = json.loads((source / (name + ".json")).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Cannot read upstream config: {name}") from error
        if set(config) - {"name", "normalization", "conversion_chain", "segmentation"}:
            raise ValueError(f"Unknown OpenCC config fields: {name}")
        stages = config.get("normalization", []) + config["conversion_chain"]
        if not stages or any(set(stage) != {"dict"} for stage in stages):
            raise ValueError(f"Unsupported conversion stages: {name}")
        chain = [{"dict": dictionary(stage["dict"])} for stage in stages]
        segmentation = config.get("segmentation")
        if segmentation is not None:
            if set(segmentation) != {"type", "dict"} or segmentation["type"] != "mmseg":
                raise ValueError("Only mmseg segmentation is supported")
            segment_dict = dictionary(segmentation["dict"])
        else:
            segment_dict = dictionary(config["conversion_chain"][0]["dict"])
        # Rime ConvertWord bypasses OpenCC normalization; keep it in the chain.
        result = {
            "name": config["name"],
            "segmentation": {"type": "mmseg", "dict": segment_dict},
            "conversion_chain": chain,
        }
        (target / (PREFIX + name + ".json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def generate_schema(source: dict, family: str, suffix: str) -> dict:
    schema = source["schema"]
    sid = schema["schema_id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", sid) or suffix not in ("大陆", "大陸"):
        raise ValueError("Invalid schema ID or name suffix")
    switches = copy.deepcopy(source["switches"])
    filters = list(source["engine"].get("filters", []))
    government: dict = {
        "option_name": "gov_traditional",
        "opencc_config": PREFIX + "t2gov_keep_simp.json",
        "tips": "none",
    }
    patch = {
        "switches": switches,
        "engine/filters": filters,
        "gov_traditional": government,
    }
    if family == "ice":
        if filters.count("simplifier@traditionalize") != 1 or not any(
            s.get("name") == "traditionalization" for s in switches
        ):
            raise ValueError("Unsupported ice traditionalization structure")
        original = source["traditionalize"]
        if (
            original.get("option_name") != "traditionalization"
            or original.get("opencc_config") != "s2t.json"
        ):
            raise ValueError("Unsupported ice conversion config")
        government.update(copy.deepcopy(original))
        government["opencc_config"] = PREFIX + "t2gov_keep_simp.json"
        filters.insert(
            filters.index("simplifier@traditionalize") + 1, "simplifier@gov_traditional"
        )
    elif family in ("luna", "cangjie"):
        option = "zh_hans" if family == "luna" else "simplification"
        matches = [
            i
            for i, switch in enumerate(switches)
            if switch.get("name") == option or option in switch.get("options", [])
        ]
        if len(matches) != 1:
            raise ValueError(f"Unsupported {family} switch structure")
        index = matches[0]
        old = switches[index]
        reset = old.get("reset", 0)
        if reset not in (0, 1):
            raise ValueError("Unexpected default character mode")
        switches[index] = {
            "options": ["gov_traditional", option],
            "states": ["大陸繁體", "简体"],
            "reset": reset,
        }
        if family == "luna":
            old_filters = [
                "simplifier@zh_hans",
                "simplifier@zh_hant_hk",
                "simplifier@zh_hant_tw",
            ]
            if any(filters.count(f) != 1 for f in old_filters):
                raise ValueError("Unsupported luna conversion filters")
            filters[:] = [f for f in filters if f not in old_filters[1:]]
            filters.insert(
                filters.index(old_filters[0]) + 1, "simplifier@gov_traditional"
            )
            government["excluded_types"] = ["reverse_lookup"]
        else:
            if filters.count("simplifier") != 1:
                raise ValueError("Unsupported cangjie conversion filters")
            filters.insert(
                filters.index("simplifier") + 1, "simplifier@gov_traditional"
            )
    elif family == "wubi":
        if any("simplifier" in f for f in filters) or any(
            s.get("name") == "zh_trad" for s in switches
        ):
            raise ValueError("Wubi upstream already has a conversion filter/switch")
        switches.append(
            {"name": "gov_traditional", "states": ["简体", "大陸繁體"], "reset": 0}
        )
        government["opencc_config"] = PREFIX + "s2t.json"
        government["excluded_types"] = ["reverse_lookup"]
        filters.insert(
            filters.index("uniquifier") if "uniquifier" in filters else len(filters),
            "simplifier@gov_traditional",
        )
    else:
        raise ValueError(f"Unsupported family: {family}")
    if "uniquifier" not in filters:
        filters.append("uniquifier")
    if filters.index("simplifier@gov_traditional") > filters.index("uniquifier"):
        raise ValueError("Upstream deduplication runs before conversion")
    # Deployment reads schema_id before expanding __include or __patch.
    header = {
        "schema_id": sid + "_gov",
        "name": schema["name"] + suffix,
        "version": str(schema.get("version", "1")) + ".gov",
    }
    return {"schema": header, "__include": sid + ".schema:/", "__patch": patch}


def name_suffix(name: str) -> str:
    simplified = subprocess.run(
        ["opencc", "-c", "t2s.json"],
        input=name,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    traditional = subprocess.run(
        ["opencc", "-c", "s2t.json"],
        input=name,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if simplified == name and traditional != name:
        return "大陆"
    if traditional == name and simplified != name:
        return "大陸"
    raise ValueError(f"Ambiguous display name needs explicit suffix: {name}")


def discover_schemas(upstreams: Path) -> list:
    paths = [(upstreams / "rime-ice/rime_ice.schema.yaml", "ice")]
    paths += [
        (p, "ice")
        for p in sorted((upstreams / "rime-ice").glob("double_pinyin*.schema.yaml"))
    ]
    paths += [
        (upstreams / f"{repo}/{sid}.schema.yaml", family)
        for repo, sid, family in (
            ("rime-luna-pinyin", "luna_pinyin", "luna"),
            ("rime-cangjie", "cangjie5", "cangjie"),
            ("rime-wubi", "wubi86", "wubi"),
        )
    ]
    result = []
    for path, family in paths:
        # Read only top-level blocks used by the adapter. Other upstream blocks
        # contain yaml-cpp-compatible literal tabs that PyYAML rejects.
        blocks = re.split(
            r"(?=^[A-Za-z_][A-Za-z0-9_]*:)",
            path.read_text(encoding="utf-8-sig"),
            flags=re.MULTILINE,
        )
        selected = "".join(
            block
            for block in blocks
            if block.split(":", 1)[0]
            in ("schema", "switches", "engine", "traditionalize")
        )
        data = yaml.safe_load(selected)
        if not isinstance(data, dict) or data.get("schema", {}).get(
            "schema_id"
        ) != path.name.removesuffix(".schema.yaml"):
            raise ValueError(f"Unsupported schema file: {path}")
        result.append((data, family))
    return result


def build(upstreams: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    gov = (
        upstreams
        / "OpenCC-Traditional-Chinese-characters-according-to-Chinese-government-standards"
    )
    compile_opencc(gov / "t2gov", output / "opencc")
    entries = []
    for source, family in discover_schemas(upstreams):
        sid = source["schema"]["schema_id"]
        # 朙月拼音 has no distinguishing simplified/traditional characters.
        suffix = (
            "大陸"
            if sid == "luna_pinyin" and source["schema"]["name"] == "朙月拼音"
            else name_suffix(source["schema"]["name"])
        )
        derived = generate_schema(source, family, suffix)
        (output / (sid + "_gov.schema.yaml")).write_text(
            yaml.safe_dump(derived, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        entries.append(
            {
                "id": sid + "_gov",
                "base": sid,
                "family": family,
                "name": derived["schema"]["name"],
            }
        )
    (output / "schemes.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    licenses = output / "licenses"
    licenses.mkdir()
    for repo in (gov.name, "rime-ice", "rime-luna-pinyin", "rime-cangjie", "rime-wubi"):
        candidates = sorted((upstreams / repo).glob("LICENSE*"))
        if not candidates:
            raise ValueError(f"Upstream license missing: {repo}")
        for license_file in candidates:
            shutil.copyfile(license_file, licenses / (repo + "-" + license_file.name))
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "README.md", output / "README.md"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstreams", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New, non-existing output directory"
    )
    args = parser.parse_args()
    build(args.upstreams, args.output)
