"""Catch month-boundary scheduling drift and publishing unverified packages."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path


def release_module():
    path = Path(__file__).resolve().parents[1] / "scripts/release.py"
    if not path.exists():
        raise AssertionError("release helper is not implemented")
    spec = importlib.util.spec_from_file_location("release", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    def test_three_day_slots_do_not_reset_at_month_boundary(self):
        module = release_module()
        self.assertTrue(module.scheduled_day(date(2026, 9, 9)))
        self.assertTrue(module.scheduled_day(date(2026, 9, 30)))
        self.assertFalse(module.scheduled_day(date(2026, 10, 1)))
        self.assertTrue(module.scheduled_day(date(2026, 10, 3)))
        self.assertFalse(module.scheduled_day(date(2026, 12, 31)))
        self.assertTrue(module.scheduled_day(date(2027, 1, 1)))
        self.assertFalse(module.scheduled_day(date(2027, 1, 2)))

    def test_input_key_changes_for_data_but_not_upstream_readme(self):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data.txt").write_text("偽\t僞\n", encoding="utf-8")
            before = module.fingerprint(root)
            (root / "README.md").write_text("documentation changed")
            self.assertEqual(module.fingerprint(root), before)
            (root / "data.txt").write_text("偽\t偽\n", encoding="utf-8")
            self.assertNotEqual(module.fingerprint(root), before)

    def test_pack_requires_all_schemes_verified_and_rejects_overwrite_files(self):
        module = release_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            (package / "opencc").mkdir()
            (package / "schemes.json").write_text(json.dumps([{"id": "demo_gov"}]))
            (package / "demo_gov.schema.yaml").write_text("schema: {}\n")
            (package / "opencc/govrime_test.json").write_text("{}")
            (package / "README.md").write_text("instructions")
            report: dict = {"schemes": []}
            with self.assertRaises(ValueError):
                module.pack(package, report, {}, root / "output.zip")
            report["schemes"] = [
                {
                    "id": "demo_gov",
                    "simplified_unchanged": True,
                    "traditional_unique": True,
                    "default_correct": True,
                }
            ]
            report["files"] = {
                p.relative_to(package).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in package.rglob("*")
                if p.is_file()
            }
            module.pack(package, report, {}, root / "output.zip")
            self.assertTrue((root / "output.zip").is_file())
            (package / "demo_gov.schema.yaml").write_text("schema: {name: changed}\n")
            with self.assertRaises(ValueError):
                module.pack(package, report, {}, root / "changed.zip")
            (package / "opencc/s2t.json").write_text("{}")
            with self.assertRaises(ValueError):
                module.pack(package, report, {}, root / "unsafe.zip")


if __name__ == "__main__":
    unittest.main()
