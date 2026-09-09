"""Small read-only upstream fetcher, three-day calendar gate, and ZIP packer."""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

REPOSITORIES = (
    "TerryTian-tech/OpenCC-Traditional-Chinese-characters-according-to-Chinese-government-standards",
    "iDvel/rime-ice",
    "rime/rime-luna-pinyin",
    "rime/rime-cangjie",
    "rime/rime-wubi",
    "rime/rime-prelude",
    "rime/rime-stroke",
    "rime/rime-pinyin-simp",
    "rime/rime-essay",
    "BYVoid/OpenCC",
)


def scheduled_day(day: date) -> bool:
    return (day - date(2026, 9, 9)).days % 3 == 0


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON: {path}") from error


def fetch(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    revisions = {}
    for repository in REPOSITORIES:
        destination = root / repository.split("/")[-1]
        ref = ["--branch", "ver.1.1.9"] if repository == "BYVoid/OpenCC" else []
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                *ref,
                "--",
                f"https://github.com/{repository}.git",
                str(destination),
            ],
            check=True,
        )
        revisions[repository] = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    return revisions


def fingerprint(root: Path) -> str:
    """Content key excludes docs and Git metadata, but includes conversion assets."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            any(part.startswith(".") for part in relative.parts)
            or path.is_symlink()
            or not path.is_file()
        ):
            continue
        if path.suffix not in (
            ".yaml",
            ".txt",
            ".json",
            ".lua",
            ".ocd2",
            ".py",
            ".c",
        ) and not path.name.startswith("LICENSE"):
            continue
        digest.update(str(relative).encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def pack(package: Path, report: dict, revisions: dict, output: Path) -> None:
    entries = read_json(package / "schemes.json")
    ids = {entry["id"] for entry in entries}
    verified = report.get("schemes", [])
    if (
        not ids
        or len(verified) != len(ids)
        or {entry["id"] for entry in verified} != ids
    ):
        raise ValueError("Not all packaged schemes were verified")
    if not all(
        isinstance(entry.get(key), bool) and entry[key]
        for entry in verified
        for key in ("simplified_unchanged", "traditional_unique", "default_correct")
    ):
        raise ValueError("A verification gate failed")
    files = []
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Package symlink: {path}")
        if not path.is_file():
            continue
        name = path.relative_to(package).as_posix()
        allowed = (
            name in {"README.md", "schemes.json"}
            or name in {sid + ".schema.yaml" for sid in ids}
            or re.fullmatch(r"opencc/govrime_[A-Za-z0-9_]+\.(json|ocd2)", name)
            or re.fullmatch(r"licenses/[A-Za-z0-9_.-]+", name)
        )
        if not allowed:
            raise ValueError(f"Unexpected package file: {name}")
        files.append((path, name))
    manifest = {
        "upstreams": revisions,
        "files": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files
        },
    }
    if report.get("files") != manifest["files"]:
        raise ValueError("Package changed after verification")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        archive.writestr(
            "verification.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scheduled")
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("directory", type=Path)
    fetch_parser.add_argument("manifest", type=Path)
    key_parser = sub.add_parser("fingerprint")
    key_parser.add_argument("directory", type=Path)
    pack_parser = sub.add_parser("pack")
    for name in ("package", "report", "revisions", "output"):
        pack_parser.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.command == "scheduled":
        print("true" if scheduled_day(datetime.now(UTC).date()) else "false")
    elif args.command == "fetch":
        args.manifest.write_text(
            json.dumps(fetch(args.directory), indent=2) + "\n", encoding="utf-8"
        )
    elif args.command == "fingerprint":
        print(fingerprint(args.directory))
    else:
        pack(
            args.package, read_json(args.report), read_json(args.revisions), args.output
        )
