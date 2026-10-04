"""Build pipeline and honesty rules: determinism, exit codes, empty/stale states, no invented numbers."""

import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import BUILD_DATE, REPO_ROOT, SCRIPTS, empty_dir, is_value_object, snapshot, synthetic_copy, synthetic_dir, walk

from agame.build import build
from agame.compute import muscles
from agame.compute.ctx import Ctx
from agame.datastore import load_all
from agame.paths import load_config

from helpers import _TMP as _TMPROOT  # noqa: E402

WEB = SCRIPTS / "agame" / "web"


def tmpdist():
    return Path(tempfile.mkdtemp(prefix="dist-", dir=_TMPROOT))


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dist_a, cls.dist_b = tmpdist(), tmpdist()
        cls.rep_a = build(synthetic_dir(), cls.dist_a, BUILD_DATE)
        cls.rep_b = build(synthetic_dir(), cls.dist_b, BUILD_DATE)

    def test_ok_with_synthetic(self):
        self.assertEqual((self.rep_a["status"], self.rep_a["exit_code"]), ("ok", 0), self.rep_a["errors"])
        for f in ("fitness_dashboard.html", "build_report.json", "morning_summary.json", "weekly_review.json", "widgets.json",
                  "manifest.webmanifest", "fitness_sw.js"):
            self.assertTrue((self.dist_a / f).is_file(), f)

    def test_deterministic(self):
        self.assertEqual(self.rep_a["output_hash"], self.rep_b["output_hash"])
        for f in self.rep_a["outputs"]:
            self.assertEqual((self.dist_a / f).read_bytes(), (self.dist_b / f).read_bytes(), f)

    def test_report_is_machine_readable(self):
        rep = json.loads((self.dist_a / "build_report.json").read_text())
        for k in ("contract", "status", "exit_code", "errors", "warnings", "degraded_reasons", "freshness", "output_hash", "data_dir_hashes"):
            self.assertIn(k, rep)

    def test_empty_is_degraded_not_failed(self):
        d = tmpdist()
        rep = build(empty_dir(), d, BUILD_DATE)
        self.assertEqual((rep["status"], rep["exit_code"]), ("degraded", 2))
        self.assertTrue(rep["degraded_reasons"])
        html = (d / "fitness_dashboard.html").read_text()
        self.assertNotIn("Synthetic Athlete", html)

    def test_impossible_data_fails_and_keeps_previous_build(self):
        d = tmpdist()
        src = synthetic_copy()
        self.assertEqual(build(src, d, BUILD_DATE)["exit_code"], 0)
        before = (d / "fitness_dashboard.html").read_bytes()
        w = json.loads((src / "workouts.json").read_text())
        w["workouts"][-1]["max_hr"] = 330
        (src / "workouts.json").write_text(json.dumps(w))
        rep = build(src, d, BUILD_DATE)
        self.assertEqual((rep["status"], rep["exit_code"]), ("failed", 1))
        self.assertTrue(any("heart rate" in e["message"] for e in rep["errors"]))
        self.assertEqual((d / "fitness_dashboard.html").read_bytes(), before)
        self.assertEqual(json.loads((d / "build_report.json").read_text())["status"], "failed")

    def test_partial_data_builds(self):
        src = synthetic_copy()
        (src / "nutrition.json").unlink()
        (src / "strength.json").unlink()
        rep = build(src, tmpdist(), BUILD_DATE)
        self.assertEqual(rep["exit_code"], 0, rep["errors"])  # optional modules: warn only
        self.assertTrue(any("nutrition.json" in w["message"] for w in rep["warnings"]))
        (src / "sleep.json").unlink()
        rep = build(src, tmpdist(), BUILD_DATE)
        self.assertEqual(rep["exit_code"], 2, rep["errors"])  # core domain missing: degraded
        self.assertTrue(any("sleep" in r for r in rep["degraded_reasons"]))

    def test_snapshot_retention(self):
        from datetime import timedelta
        d = tmpdist()
        for k in range(9):
            build(empty_dir(), d, BUILD_DATE - timedelta(days=k))
        self.assertEqual(len(list((d / "snapshots").glob("*.html"))), 7)

    def test_cli_exit_codes(self):
        cli = [sys.executable, str(SCRIPTS / "build_dashboard.py"), "--quiet", "--out", str(tmpdist())]
        self.assertEqual(subprocess.run(cli + ["--date", "2026-10-04", "--data-dir", str(REPO_ROOT / "data")], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(cli + ["--date", "2026-10-04", "--data-dir", "/nonexistent"], capture_output=True).returncode, 1)
        self.assertNotEqual(subprocess.run(cli + ["--date", "not-a-date"], capture_output=True).returncode, 0)


class Honesty(unittest.TestCase):
    def test_missing_values_are_null_never_zero(self):
        for kind in ("synthetic", "empty"):
            snap, _ = snapshot(kind)
            for path, v in walk(snap):
                if is_value_object(v) and v["status"] == "missing":
                    self.assertIsNone(v["v"], f"{kind}{path}")

    def test_every_number_has_as_of(self):
        snap, _ = snapshot()
        for path, v in walk(snap):
            if is_value_object(v) and v["v"] is not None:
                self.assertTrue(v.get("as_of"), f"{path} has a value but no as_of")

    def test_empty_snapshot_invents_nothing(self):
        snap, _ = snapshot("empty")
        self.assertEqual(snap["activities"]["list"], [])
        self.assertEqual(snap["goals"], [])
        for ring in snap["today"]["rings"].values():
            self.assertIsNone(ring["v"])
        self.assertEqual(snap["today"]["action"]["id"], "no_data")
        self.assertIsNone(snap["profile"]["display_name"])
        for path, v in walk(snap["training"]["pmc"]):
            self.assertFalse(isinstance(v, (int, float)) and not isinstance(v, bool) and path.endswith(("/ctl", "/atl", "/tsb")), path)

    def test_stale_sleep_is_marked(self):
        from agame.synthetic import write_synthetic
        from agame.snapshot import build_snapshot
        out = write_synthetic(tempfile.mkdtemp(dir=_TMPROOT), BUILD_DATE, missing_last_sleep=True)
        data, _, _ = load_all(out)
        snap, _ = build_snapshot(data, BUILD_DATE)
        self.assertTrue(snap["sleep"]["stale"])
        self.assertEqual(snap["sleep"]["score"]["status"], "stale")
        self.assertNotEqual(snap["meta"]["data_status"]["domains"]["sleep"]["status"], "ok")

    def test_no_banned_medical_phrases(self):
        banned = load_config()["insights"]["banned_phrases"]
        snap, _ = snapshot()
        for path, v in walk({k: snap[k] for k in snap if k not in ("health", "meta")}):
            if isinstance(v, str):
                low = v.lower()
                for b in banned:
                    self.assertNotIn(b, low, f"{path}: {v!r}")

    def test_power_curve_empty_without_power(self):
        snap, _ = snapshot()
        for wid, det in snap["activities"]["details"].items():
            if not any(p.get("power_w") for p in (det["series"] or {}).get("points", []) if isinstance(p, dict)) and det["row"]["family"] != "run":
                self.assertFalse(det["power_curve"], wid)

    def test_no_muscles_from_generic_strength_workouts(self):
        data, _, _ = load_all(synthetic_dir())
        d = copy.deepcopy(data)
        d["strength"]["sessions"] = []
        ms = muscles.muscle_status(Ctx(d, BUILD_DATE))
        self.assertFalse(ms["has_exercise_logs"])
        self.assertGreater(ms["unlogged_strength_workouts"], 0)
        mapped = {m for groups in load_config()["muscles"]["cardio_mapping"].values() for m in groups}
        for name, g in ms["groups"].items():
            if name not in mapped:
                self.assertEqual(g["load_status"], "no_data", name)


class FrontendRules(unittest.TestCase):
    """The browser renders; Python computes. No second definition of any score in JS."""

    def js(self):
        return {p.name: p.read_text() for p in WEB.glob("*.js")}

    def test_no_formulas_in_js(self):
        forbidden = [r"220\s*-", r"\b1\.92\b", r"\b0\.64\b", r"\b1\.67\b", r"/\s*42\b", r"1\s*/\s*7\b", r"\btrimp\s*\(", r"\bewma\b",
                     r"Math\.exp\(", r"\bstdev\b", r"\bmedian\s*\("]
        for name, src in self.js().items():
            for pat in forbidden:
                for m in re.finditer(pat, src):
                    line = src[:m.start()].count("\n") + 1
                    if name == "charts.js" and pat == r"Math\.exp\(":
                        continue  # log-scale axis labels only
                    self.fail(f"{name}:{line} matches forbidden formula pattern {pat}")

    def test_js_does_not_read_raw_inputs(self):
        for name, src in self.js().items():
            self.assertNotRegex(src, r"\bD\.(metrics|workouts)\.(series|workouts)\b", name)

    def test_no_hard_coded_people_dates_or_targets(self):
        for name, src in self.js().items():
            self.assertNotRegex(src, r"\b20[2-3]\d-\d\d-\d\d\b", f"{name} contains a hard-coded date")
            self.assertNotIn("Synthetic Athlete", src, name)
            self.assertNotRegex(src, r"(?i)\b(steve|christian|tonny)\b", name)

    def test_no_strava_or_bevel_api(self):
        for p in list(SCRIPTS.rglob("*.py")) + list(WEB.glob("*.js")):
            if "tests" in p.parts:
                continue
            src = p.read_text().lower()
            self.assertNotIn("strava.com/api", src, p)
            self.assertNotIn("api.bevel", src, p)


if __name__ == "__main__":
    unittest.main()
