"""Small read-only upstream fetcher, three-day calendar gate, and ZIP packer."""

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
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


def require_verified(ids: set, verified: list) -> None:
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


def pack(package: Path, report: dict, revisions: dict, output: Path) -> None:
    entries = read_json(package / "schemes.json")
    ids = {entry["id"] for entry in entries}
    require_verified(ids, report.get("schemes", []))
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


def verified_archive(path: Path) -> dict:
    """Validate before extracting; never trust ZIP paths or its verification claim alone."""
    metadata = {"manifest.json", "verification.json"}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != len({entry.filename for entry in entries}):
            raise ValueError("Duplicate archive paths")
        if sum(entry.file_size for entry in entries) > 128 * 1024 * 1024:
            raise ValueError("Archive exceeds the 128 MiB snapshot limit")
        for entry in entries:
            allowed = (
                entry.filename in metadata | {"README.md", "schemes.json"}
                or re.fullmatch(r"[a-z][a-z0-9_]*_gov\.schema\.yaml", entry.filename)
                or re.fullmatch(
                    r"opencc/govrime_[A-Za-z0-9_]+\.(json|ocd2)", entry.filename
                )
                or re.fullmatch(r"licenses/[A-Za-z0-9][A-Za-z0-9_.-]*", entry.filename)
            )
            if not allowed or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f"Unsafe archive entry: {entry.filename}")
        files = {entry.filename: archive.read(entry) for entry in entries}
    try:
        manifest = json.loads(files["manifest.json"])
        report = json.loads(files["verification.json"])
        ids = {entry["id"] for entry in json.loads(files["schemes.json"])}
        hashes = {
            name: hashlib.sha256(data).hexdigest()
            for name, data in files.items()
            if name not in metadata
        }
        if hashes != manifest["files"] or hashes != report["files"]:
            raise ValueError("Archive does not match verified file hashes")
        if {name for name in files if name.endswith(".schema.yaml")} != {
            sid + ".schema.yaml" for sid in ids
        }:
            raise ValueError("Archive scheme list is incomplete")
        require_verified(ids, report["schemes"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid archive metadata") from error
    return files


def sync_archive(archive: Path, target: Path) -> None:
    """Replace only an unchanged, managed snapshot, after verifying all ZIP bytes."""
    files = verified_archive(archive)
    marker = "GENERATED.json"
    if target.is_symlink():
        raise ValueError("Snapshot directory must not be a symlink")
    if target.exists():
        existing = {}
        for path in target.rglob("*"):
            if path.is_symlink():
                raise ValueError("Snapshot contains a symlink")
            name = path.relative_to(target).as_posix()
            if path.is_file() and name != marker:
                existing[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt = read_json(target / marker)
        if (
            receipt.get("generator") != "OpenCCGovForRime"
            or receipt.get("files") != existing
        ):
            raise ValueError("Snapshot has manual changes; refusing to overwrite")
    receipt = {
        "generator": "OpenCCGovForRime",
        "notice": "自动生成，请勿手动编辑。Generated by Actions; do not edit.",
        "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".govrime-sync-", dir=target.parent))
    staging, backup = temp / "new", temp / "old"
    installed = False
    try:
        staging.mkdir()
        for name, data in files.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (staging / marker).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if target.exists():
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup.exists():
                backup.rename(target)
            raise
        installed = True
    finally:
        # If rollback also failed, retain the old snapshot for recovery.
        if installed or not backup.exists():
            shutil.rmtree(temp)


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
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("archive", type=Path)
    sync_parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "scheduled":
        print("true" if scheduled_day(datetime.now(UTC).date()) else "false")
    elif args.command == "fetch":
        args.manifest.write_text(
            json.dumps(fetch(args.directory), indent=2) + "\n", encoding="utf-8"
        )
    elif args.command == "fingerprint":
        print(fingerprint(args.directory))
    elif args.command == "sync":
        sync_archive(args.archive, args.directory)
    else:
        pack(
            args.package, read_json(args.report), read_json(args.revisions), args.output
        )
