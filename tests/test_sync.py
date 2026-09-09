"""Repository snapshots must match verified ZIPs and preserve unmanaged data."""

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import yaml


def release_module():
    path = Path(__file__).resolve().parents[1] / "scripts/release.py"
    spec = importlib.util.spec_from_file_location("release", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(path, sid="demo_gov", extra=None, corrupt=False, symlink=False):
    files = {
        f"{sid}.schema.yaml": b"schema: {}\n",
        "README.md": b"instructions\n",
        "schemes.json": json.dumps([{"id": sid}]).encode(),
    }
    if extra:
        files.update(extra)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    report = {
        "files": hashes,
        "schemes": [
            {
                "id": sid,
                "simplified_unchanged": True,
                "traditional_unique": True,
                "default_correct": True,
            }
        ],
    }
    files["manifest.json"] = json.dumps({"files": hashes, "upstreams": {}}).encode()
    files["verification.json"] = json.dumps(report).encode()
    if corrupt:
        files["README.md"] = b"unverified change"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            if symlink and name == "README.md":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, data)
    return files


class SyncTests(unittest.TestCase):
    def test_workflow_commits_only_snapshot_and_skips_unchanged_commits(self):
        project = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load(
            (project / ".github/workflows/release.yml").read_text()
        )
        steps = [
            step
            for step in workflow["jobs"]["publish"]["steps"]
            if step.get("id") == "sync"
        ]
        self.assertEqual(len(steps), 1, "snapshot publishing step is missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, worker = root / "remote.git", root / "worker"
            subprocess.run(
                ["git", "init", "--bare", str(remote)], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "init", "-b", "master", str(worker)],
                check=True,
                capture_output=True,
            )

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(worker), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (worker / "scripts").mkdir()
            shutil.copyfile(
                project / "scripts/release.py", worker / "scripts/release.py"
            )
            (worker / "README.md").write_text("original")
            git("add", "scripts", "README.md")
            git("commit", "-m", "baseline")
            git("remote", "add", "origin", str(remote))
            git("push", "-u", "origin", "master")
            (worker / "README.md").write_text("unrelated staged change")
            git("add", "README.md")
            (worker / "dist").mkdir()
            fixture(worker / "dist/OpenCCGovForRime.zip")
            env = {
                **os.environ,
                "BRANCH": "master",
                "GITHUB_OUTPUT": str(root / "outputs"),
            }
            command = ["bash", "-euo", "pipefail", "-c", steps[0]["run"]]
            subprocess.run(
                command, cwd=worker, env=env, check=True, capture_output=True, text=True
            )
            first = git("rev-parse", "HEAD")
            self.assertEqual(git("show", "HEAD:README.md"), "original")
            self.assertEqual(git("diff", "--cached", "--name-only"), "README.md")
            published = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "show",
                    "master:rime/demo_gov.schema.yaml",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(published, "schema: {}\n")
            subprocess.run(
                command, cwd=worker, env=env, check=True, capture_output=True, text=True
            )
            self.assertEqual(git("rev-parse", "HEAD"), first)

    def test_verified_files_sync_idempotently_and_remove_obsolete_generated_files(self):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second, target = (
                root / "first.zip",
                root / "second.zip",
                root / "rime",
            )
            files = fixture(first)
            module.sync_archive(first, target)
            for name, data in files.items():
                self.assertEqual((target / name).read_bytes(), data)
            receipt = (target / "GENERATED.json").read_bytes()
            module.sync_archive(first, target)
            self.assertEqual((target / "GENERATED.json").read_bytes(), receipt)
            fixture(second, "next_gov")
            module.sync_archive(second, target)
            self.assertFalse((target / "demo_gov.schema.yaml").exists())
            self.assertTrue((target / "next_gov.schema.yaml").is_file())

    def test_invalid_archives_leave_the_existing_snapshot_and_outside_files_untouched(
        self,
    ):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            valid, target = root / "valid.zip", root / "rime"
            files = fixture(valid)
            module.sync_archive(valid, target)
            outside = root / "outside.txt"
            outside.write_text("keep")
            cases: list[dict] = [
                {"extra": {"../outside.txt": b"overwrite"}},
                {"extra": {"opencc/s2t.json": b"{}"}},
                {"corrupt": True},
                {"symlink": True},
            ]
            for index, options in enumerate(cases):
                with self.subTest(options=options):
                    bad = root / f"bad-{index}.zip"
                    fixture(bad, **options)
                    with self.assertRaises(ValueError):
                        module.sync_archive(bad, target)
                    self.assertEqual(
                        (target / "README.md").read_bytes(), files["README.md"]
                    )
                    self.assertEqual(outside.read_text(), "keep")

    def test_failed_install_and_rollback_preserve_the_backup(self):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive, target = root / "valid.zip", root / "rime"
            files = fixture(archive)
            module.sync_archive(archive, target)
            rename = Path.rename

            def fail_replacement(path, destination):
                if path.name in ("new", "old"):
                    raise OSError("simulated filesystem failure")
                return rename(path, destination)

            with (
                patch.object(Path, "rename", fail_replacement),
                self.assertRaises(OSError),
            ):
                module.sync_archive(archive, target)
            backups = list(root.glob(".govrime-sync-*/old/README.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), files["README.md"])

    def test_unmanaged_or_manually_changed_directories_are_not_overwritten(self):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "valid.zip"
            fixture(archive)
            unmanaged = root / "manual"
            unmanaged.mkdir()
            (unmanaged / "notes.txt").write_text("keep")
            with self.assertRaises(ValueError):
                module.sync_archive(archive, unmanaged)
            self.assertEqual((unmanaged / "notes.txt").read_text(), "keep")
            target = root / "rime"
            module.sync_archive(archive, target)
            (target / "README.md").write_text("my edits")
            with self.assertRaises(ValueError):
                module.sync_archive(archive, target)
            self.assertEqual((target / "README.md").read_text(), "my edits")


if __name__ == "__main__":
    unittest.main()
