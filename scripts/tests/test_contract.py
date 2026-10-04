"""Data contract: schemas, empty fixtures, migrations, semantic checks, public-repo guard."""

import json
import re
import subprocess
import unittest

from helpers import BUILD_DATE, REPO_ROOT, empty_dir, synthetic_copy, synthetic_dir

from agame import SCHEMA_VERSION
from agame.datastore import load_all
from agame.empty import empty_payload
from agame.migrate import MigrationError, migrate
from agame.paths import DATA_FILES, domain_of
from agame.schema_defs import EXTRA, build_all
from agame.validate import validate_data


def _rw(path, fn):
    obj = json.loads(path.read_text())
    fn(obj)
    path.write_text(json.dumps(obj))


class SchemaFiles(unittest.TestCase):
    def test_schema_files_match_schema_defs(self):
        for name, sch in list(build_all().items()) + [(k, fn()) for k, fn in EXTRA.items()]:
            on_disk = json.loads((REPO_ROOT / "schemas" / f"{name}.schema.json").read_text())
            self.assertEqual(on_disk, sch, f"schemas/{name}.schema.json is stale; run python3 -m agame.schema_defs --write")

    def test_every_data_file_has_a_schema(self):
        names = set(build_all())
        for f in DATA_FILES:
            self.assertIn(domain_of(f), names)


class EmptyFixtures(unittest.TestCase):
    def test_repo_fixtures_are_valid_and_empty(self):
        rep, _ = validate_data(REPO_ROOT / "data", BUILD_DATE)
        self.assertEqual(rep.errors, [])
        for f in DATA_FILES:
            obj = json.loads((REPO_ROOT / "data" / f).read_text())
            self.assertEqual(obj["fixture"], "empty", f)
            self.assertEqual(obj["schema_version"], SCHEMA_VERSION, f)
            self.assertEqual(obj, json.loads(json.dumps(empty_payload(domain_of(f)))), f"{f} differs from empty_payload()")

    def test_missing_files_are_treated_as_empty(self):
        d = empty_dir()
        (d / "nutrition.json").unlink()
        data, problems, _ = load_all(d)
        self.assertEqual(problems, [])
        self.assertEqual(data["nutrition"]["status"], "missing")
        self.assertEqual(data["nutrition"]["meals"], [])
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertEqual(rep.errors, [])

    def test_synthetic_is_valid(self):
        rep, _ = validate_data(synthetic_dir(), BUILD_DATE)
        self.assertEqual(rep.errors, [])


class PublicRepoGuard(unittest.TestCase):
    """The repo is public: only empty fixtures and no secrets may be tracked."""

    def tracked(self):
        out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        return out.stdout.split()

    def test_only_empty_fixtures_in_data(self):
        for f in self.tracked():
            if f.startswith("data/"):
                obj = json.loads((REPO_ROOT / f).read_text())
                self.assertEqual(obj.get("fixture"), "empty", f"{f} is tracked but not an empty fixture")

    def test_no_private_files_tracked(self):
        banned = re.compile(r"(^|/)(\.env|edit_history\.jsonl|.*\.local\.json)$|^(dist|snapshots|private|uploads)/(?!\.gitkeep$)")
        for f in self.tracked():
            if f == ".env.example":
                continue
            self.assertIsNone(banned.search(f), f"{f} must not be tracked")

    def test_env_example_has_names_only(self):
        for line in (REPO_ROOT / ".env.example").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                name, _, value = line.partition("=")
                self.assertRegex(name, r"^[A-Z_]+$")
                self.assertEqual(value.strip(), "", f"{name} has a value in .env.example")

    def test_no_secret_like_strings_in_source(self):
        pat = re.compile(r"sk-ant-[A-Za-z0-9]|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20}")
        for f in self.tracked():
            p = REPO_ROOT / f
            if p.suffix in (".py", ".js", ".json", ".md", ".toml", ".sh", ".html", ".css", "") and p.is_file():
                self.assertIsNone(pat.search(p.read_text(errors="ignore")), f)


class Migrations(unittest.TestCase):
    def test_old_version_migrates(self):
        p = {"schema_version": "0.9.0", "sessions": [], "domain": "sleep"}
        out, warnings = migrate("sleep", p)
        self.assertEqual(out["schema_version"], SCHEMA_VERSION)
        self.assertIn("nights", out)
        self.assertTrue(warnings)

    def test_newer_version_fails(self):
        with self.assertRaises(MigrationError):
            migrate("sleep", {"schema_version": "9.0.0"})

    def test_missing_version_fails(self):
        with self.assertRaises(MigrationError):
            migrate("sleep", {})

    def test_newer_file_fails_validation(self):
        d = empty_dir()
        _rw(d / "sleep.json", lambda o: o.update(schema_version="2.0.0"))
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertFalse(rep.ok)


class SemanticChecks(unittest.TestCase):
    def assertInvalid(self, d, needle):
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertFalse(rep.ok, "expected a validation error")
        self.assertTrue(any(needle in e["message"] for e in rep.errors), rep.errors[:5])

    def test_naive_timestamp_rejected(self):
        d = synthetic_copy()
        _rw(d / "sleep.json", lambda o: o["nights"][-1].update(end="2026-10-04T05:49:36"))
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertFalse(rep.ok)

    def test_duplicate_source_ids_rejected(self):
        d = synthetic_copy()
        _rw(d / "workouts.json", lambda o: o["workouts"].append(dict(o["workouts"][-1])))
        self.assertInvalid(d, "duplicate")

    def test_impossible_heart_rate(self):
        d = synthetic_copy()
        _rw(d / "workouts.json", lambda o: o["workouts"][-1].update(avg_hr=320))
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertFalse(rep.ok)

    def test_future_timestamp(self):
        d = synthetic_copy()
        _rw(d / "body.json", lambda o: o["measurements"].append(dict(o["measurements"][-1], source_id="x-future", t="2027-01-01T08:00:00+02:00")))
        self.assertInvalid(d, "future")

    def test_unknown_timezone(self):
        d = empty_dir()
        _rw(d / "profile.json", lambda o: o["locale"].update(timezone="Mars/Olympus"))
        self.assertInvalid(d, "timezone")

    def test_sleep_end_before_start(self):
        d = synthetic_copy()

        def f(o):
            n = o["nights"][-1]
            n["start"], n["end"] = n["end"], n["start"]
        _rw(d / "sleep.json", f)
        rep, _ = validate_data(d, BUILD_DATE)
        self.assertFalse(rep.ok)


if __name__ == "__main__":
    unittest.main()
