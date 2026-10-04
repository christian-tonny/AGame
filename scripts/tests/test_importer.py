"""HealthKit importer: idempotency, duplicates, conflicts, atomic rejection, partial syncs, CLI exit codes."""

import copy
import json
import subprocess
import sys
import unittest

from helpers import SCRIPTS, empty_dir, synthetic_dir

from agame.importer import BatchError, apply_batch
from agame.paths import DATA_FILES

_SYN = {}


def syn(name):
    if name not in _SYN:
        _SYN[name] = json.loads((synthetic_dir() / name).read_text())
    return _SYN[name]


def day_batch(day, with_sleep=True):
    m = syn("metrics.json")["series"]
    metrics = {sid: [p for p in m[sid] if (p.get("date") or p.get("t", ""))[:10] == day] for sid in ("resting_hr_bpm", "hrv_sdnn_ms", "steps")}
    return copy.deepcopy({
        "batch_version": 1, "date": day, "generated_at": f"{day}T05:40:00+02:00", "source": "healthkit",
        "samples": {
            "metrics": {k: v for k, v in metrics.items() if v},
            "sleep": [n for n in syn("sleep.json")["nights"] if n["date"] == day] if with_sleep else [],
            "workouts": [w for w in syn("workouts.json")["workouts"] if w["start"][:10] == day and not w.get("route_id")],
            "body": [b for b in syn("body.json")["measurements"] if b["t"][:10] == day],
        },
    })


def snapshot_bytes(d):
    return {f: (d / f).read_bytes() for f in DATA_FILES if (d / f).exists()}


class Importer(unittest.TestCase):
    def setUp(self):
        self.d = empty_dir()

    def test_apply_then_rerun_is_noop(self):
        b = day_batch("2026-10-02")
        summary, code = apply_batch(self.d, b)
        self.assertEqual((code, summary["status"]), (0, "applied"))
        self.assertIn("sleep", summary["domains_touched"])
        sleep = json.loads((self.d / "sleep.json").read_text())
        self.assertEqual(sleep["fixture"], False)
        self.assertEqual(len(sleep["nights"]), 1)
        before = snapshot_bytes(self.d)
        summary, code = apply_batch(self.d, copy.deepcopy(b))
        self.assertEqual((code, summary["status"]), (0, "already_imported"))
        self.assertEqual(snapshot_bytes(self.d), before)

    def test_overlapping_batch_skips_duplicates(self):
        apply_batch(self.d, day_batch("2026-10-02"))
        b = day_batch("2026-10-03")
        b["samples"]["sleep"] += day_batch("2026-10-02")["samples"]["sleep"]
        summary, code = apply_batch(self.d, b)
        self.assertEqual(code, 0)
        self.assertGreaterEqual(summary["skipped_duplicate"], 1)
        self.assertEqual(len(json.loads((self.d / "sleep.json").read_text())["nights"]), 2)

    def test_changed_record_is_a_conflict_not_an_edit(self):
        apply_batch(self.d, day_batch("2026-10-02"))
        b = day_batch("2026-10-03")
        changed = copy.deepcopy(day_batch("2026-10-02")["samples"]["metrics"]["resting_hr_bpm"][0])
        changed["v"] += 5
        b["samples"]["metrics"]["resting_hr_bpm"].append(changed)
        summary, code = apply_batch(self.d, b)
        self.assertEqual(code, 2)
        self.assertEqual(summary["conflicts"][0]["source_id"], changed["source_id"])
        stored = [p for p in json.loads((self.d / "metrics.json").read_text())["series"]["resting_hr_bpm"] if p["source_id"] == changed["source_id"]]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["v"], changed["v"] - 5)

    def test_duplicate_ids_inside_batch(self):
        b = day_batch("2026-10-02")
        p = copy.deepcopy(b["samples"]["metrics"]["resting_hr_bpm"][0])
        b["samples"]["metrics"]["resting_hr_bpm"].append(dict(p, v=p["v"] + 1))
        summary, code = apply_batch(self.d, b)
        self.assertEqual(code, 2)
        self.assertIn("same id", summary["conflicts"][0]["reason"])

    def test_invalid_batch_writes_nothing(self):
        before = snapshot_bytes(self.d)
        b = day_batch("2026-10-02")
        b["samples"]["metrics"]["resting_hr_bpm"][0]["v"] = 400
        summary, code = apply_batch(self.d, b)
        self.assertEqual((code, summary["status"]), (1, "rejected"))
        self.assertEqual(snapshot_bytes(self.d), before)

    def test_dry_run_writes_nothing(self):
        before = snapshot_bytes(self.d)
        summary, code = apply_batch(self.d, day_batch("2026-10-02"), dry_run=True)
        self.assertEqual(code, 0)
        self.assertTrue(summary["domains_touched"])
        self.assertEqual(snapshot_bytes(self.d), before)

    def test_missing_sleep_is_flagged(self):
        apply_batch(self.d, day_batch("2026-10-03", with_sleep=False) | {"samples": dict(day_batch("2026-10-03")["samples"], sleep=[])})
        cur = json.loads((self.d / "current.json").read_text())
        self.assertFalse(cur["domains"]["sleep"]["received"])
        self.assertEqual(cur["domains"]["sleep"]["note"], "Sleep not synced yet")
        self.assertTrue(cur["domains"]["metrics"]["received"])

    def test_record_without_source_id_rejected(self):
        b = day_batch("2026-10-02")
        b["samples"]["sleep"][0].pop("source_id")
        with self.assertRaises(BatchError):
            apply_batch(self.d, b)

    def test_cli_exit_codes(self):
        f = self.d / "batch.json"
        f.write_text(json.dumps(day_batch("2026-10-02")))
        cmd = [sys.executable, str(SCRIPTS / "update_from_healthkit.py"), "--date", "2026-10-02", "--input", str(f), "--data-dir", str(self.d)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "applied")
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["status"]), (0, "already_imported"))
        f.write_text("{not json")
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(cmd[:2], capture_output=True).returncode, 2)  # argparse usage error


if __name__ == "__main__":
    unittest.main()
