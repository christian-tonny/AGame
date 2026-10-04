"""muse.v1 adapter and summary imports: real Muse fixtures, units and ranges, timezones, coverage, re-sends, cross-source duplicates."""

import copy
import json
import unittest

from helpers import SCRIPTS, empty_dir

from agame import muse
from agame import timeutil as tu
from agame.importer import BatchError, apply_batch

FIX = SCRIPTS / "tests" / "fixtures"
FIELDS = json.loads((FIX / "muse-field-names.json").read_text())
DAILY = json.loads((FIX / "muse-daily-metric-row.json").read_text())


def envelope(generated_at="2026-10-04T06:15:00+02:00", sleep_complete=False):
    w = dict(FIELDS["example_workout_session"], segments=[FIELDS["example_workout_segment"]])
    cov = dict(FIELDS["sleep_coverage"], complete=sleep_complete)
    return copy.deepcopy({"format": "muse.v1", "generated_at": generated_at, "timezone": "Africa/Kigali",
                          "sleep": {"coverage": cov, "records": [FIELDS["example_sleep_session"]]},
                          "workouts": {"coverage": FIELDS["workout_coverage"], "records": [w]},
                          "daily_metrics": DAILY})


def load(d, f):
    return json.loads((d / f).read_text())


class Adapter(unittest.TestCase):
    def test_real_fixture_maps_without_rejections(self):
        batch, rejected, info = muse.to_batch(envelope())
        self.assertEqual(rejected, [])
        m = batch["samples"]["metrics"]
        self.assertAlmostEqual(m["spo2_pct"][0]["v"], DAILY["records"][0]["oxygen_saturation_average"] * 100, places=2)  # 0-1 fraction stored as %
        self.assertAlmostEqual(m["vertical_oscillation_cm"][0]["v"], DAILY["records"][0]["running_vertical_oscillation_average"] * 100, places=2)  # metres -> cm
        self.assertAlmostEqual(m["hrv_sdnn_ms"][0]["v"], DAILY["records"][0]["heart_rate_variability_ms"], places=2)
        self.assertIn("wrist_temp_c", batch["series_meta"])
        nut = batch["samples"]["nutrition"]["daily_totals"][0]
        self.assertAlmostEqual(nut["sodium_mg"], DAILY["records"][0]["dietary_sodium_sum"] * 1000, places=0)  # grams -> mg
        self.assertAlmostEqual(nut["water_ml"], DAILY["records"][0]["dietary_water_sum"], places=0)
        self.assertNotIn("record_count", json.dumps(batch))
        night = batch["samples"]["sleep"][0]
        self.assertEqual(night["start"], FIELDS["example_sleep_session"]["start_datetime"].replace(" ", "T") + "+02:00")
        self.assertNotIn("in_bed", night["stage_minutes"])  # absent stays missing, never 0
        self.assertEqual(night["awakenings"], int(FIELDS["example_sleep_session"]["number_of_awakenings"]))
        w = batch["samples"]["workouts"][0]
        self.assertEqual((w["sport"], w["indoor"], w["steps"], w["flights"]), ("walk", False, int(FIELDS["example_workout_session"]["step_count"]), int(FIELDS["example_workout_session"]["flights_climbed"])))
        self.assertEqual(w["weather"]["source"], "healthkit")
        self.assertEqual(len(w["splits"]), 1)
        self.assertEqual(w["splits"][0]["duration_s"], FIELDS["example_workout_segment"]["end_epoch_sec"] - FIELDS["example_workout_segment"]["start_epoch_sec"])

    def test_out_of_range_is_rejected_not_converted(self):
        env = envelope()
        env["daily_metrics"]["records"][0]["oxygen_saturation_average"] = 97.1  # percent instead of a fraction
        batch, rejected, _ = muse.to_batch(env)
        self.assertNotIn("spo2_pct", batch["samples"]["metrics"])
        self.assertEqual(rejected[0]["field"], "oxygen_saturation_average")
        self.assertIn("plausible range", rejected[0]["reason"])

    def test_daily_row_without_date_fails_clearly(self):
        env = envelope()
        env["daily_metrics"]["records"][0].pop("date")
        env["daily_metrics"]["records"][0]["when"] = "2026-10-04"
        _, rejected, _ = muse.to_batch(env)
        self.assertIn("needs 'date'", rejected[0]["reason"])

    def test_unknown_fields_turn_on_without_code_changes(self):
        env = envelope()
        env["daily_metrics"]["records"][0]["blood_pressure_systolic_average"] = 118.0
        env["daily_metrics"]["records"][0]["body_fat_percentage"] = 0.18
        batch, rejected, _ = muse.to_batch(env)
        self.assertEqual(rejected, [])
        self.assertEqual(batch["samples"]["metrics"]["bp_systolic_mmhg"][0]["v"], 118.0)
        self.assertEqual([b["type"] for b in batch["samples"]["body"]], ["body_fat_pct"])

    def test_ambiguous_wall_time_is_refused(self):
        with self.assertRaises(tu.AmbiguousTime):
            tu.localize("2026-11-01 01:30:00", "America/New_York")
        env = envelope()
        env["sleep"]["records"][0]["timezone"] = "America/New_York"
        env["sleep"]["records"][0]["start_datetime"] = "2026-11-01 01:30:00"
        _, rejected, _ = muse.to_batch(env)
        self.assertIn("ambiguous", rejected[0]["reason"])


class Examples(unittest.TestCase):
    def test_doc_examples_match_the_schema_and_import_cleanly(self):
        from agame.jsonschema_lite import Validator
        from agame.paths import REPO_ROOT
        schema = json.loads((REPO_ROOT / "schemas" / "healthkit_batch.schema.json").read_text())
        batch = json.loads((REPO_ROOT / "docs" / "examples" / "healthkit-batch.json").read_text())
        self.assertEqual([e.message for e in Validator(schema).validate(batch)], [])
        for name in ("healthkit-batch.json", "muse-v1-batch.json"):
            summary, code = apply_batch(empty_dir(), json.loads((REPO_ROOT / "docs" / "examples" / name).read_text()), lenient=True)
            self.assertEqual((code, summary["rejected"]), (0, []), name)


class SummaryImport(unittest.TestCase):
    def setUp(self):
        self.d = empty_dir()

    def test_import_marks_incomplete_sleep_and_resends_are_idempotent(self):
        summary, code = apply_batch(self.d, envelope(), lenient=True)
        self.assertEqual(code, 0, summary)
        cur = load(self.d, "current.json")["domains"]
        self.assertFalse(cur["sleep"]["received"])
        self.assertEqual(cur["sleep"]["note"], "Sleep not synced yet")
        self.assertTrue(load(self.d, "sleep.json")["nights"][0]["partial"])
        summary, code = apply_batch(self.d, envelope(), lenient=True)
        self.assertEqual(summary["status"], "already_imported")
        # the same three days re-sent later with the sync finished: values update, nothing duplicates
        later = envelope("2026-10-04T08:00:00+02:00", sleep_complete=True)
        later["daily_metrics"]["coverage"]["complete"] = True
        later["daily_metrics"]["records"][0]["step_count"] = 19000.0
        summary, code = apply_batch(self.d, later, lenient=True)
        self.assertEqual(code, 0, summary)
        steps = load(self.d, "metrics.json")["series"]["steps"]
        self.assertEqual([(p["v"], p.get("partial")) for p in steps], [(19000.0, None)])
        self.assertEqual(len(load(self.d, "sleep.json")["nights"]), 1)
        self.assertTrue(load(self.d, "current.json")["domains"]["sleep"]["received"])

    def test_bad_record_is_rejected_and_the_rest_applies(self):
        env = envelope()
        bad = dict(env["sleep"]["records"][0], id="healthkit_BAD", start_datetime="2026-10-04 06:00:00", end_datetime="2026-10-04 05:00:00")
        env["sleep"]["records"].append(bad)
        summary, code = apply_batch(self.d, env, lenient=True)
        self.assertEqual(code, 2)
        self.assertEqual([r["source_id"] for r in summary["rejected"]], ["healthkit_BAD"])
        self.assertEqual(len(load(self.d, "sleep.json")["nights"]), 1)
        strict, code = apply_batch(empty_dir(), copy.deepcopy(env))
        self.assertEqual((code, strict["status"]), (1, "rejected"))

    def test_broken_records_in_a_resend_are_listed_not_fatal(self):
        apply_batch(self.d, envelope(), lenient=True)
        env = envelope("2026-10-04T08:00:00+02:00")
        env["daily_metrics"]["records"][0]["oxygen_saturation_average"] = 97.0
        summary, code = apply_batch(self.d, env, lenient=True)
        self.assertEqual((code, summary["status"]), (2, "partial"))
        self.assertEqual(summary["rejected"][0]["field"], "oxygen_saturation_average")

    def test_detailed_night_replaces_the_summary_of_the_same_night(self):
        apply_batch(self.d, envelope(), lenient=True)
        night = {"source_id": "healthkit_export_night", "date": "2026-10-04", "start": "2026-10-04T00:10:00+02:00", "end": "2026-10-04T05:50:00+02:00",
                 "segments": [{"stage": "core", "start": "2026-10-04T00:15:00+02:00", "end": "2026-10-04T05:40:00+02:00"}]}
        b = {"batch_version": 2, "date": "2026-10-04", "generated_at": "2026-10-04T09:00:00+02:00", "samples": {"sleep": [night]}}
        summary, code = apply_batch(self.d, b, lenient=True)
        self.assertEqual(summary["updated"]["sleep"], 1)
        nights = load(self.d, "sleep.json")["nights"]
        self.assertEqual([n["source_id"] for n in nights], ["healthkit_export_night"])
        # Muse re-sending its summary of that night is now a duplicate, not a second night
        summary, _ = apply_batch(self.d, envelope("2026-10-04T13:00:00+02:00", sleep_complete=True), lenient=True)
        self.assertEqual(summary["duplicates"][0]["same_as"], "healthkit_export_night")
        self.assertEqual(len(load(self.d, "sleep.json")["nights"]), 1)

    def test_user_entered_records_are_never_touched(self):
        body = load(self.d, "body.json")
        body["measurements"].append({"source_id": "healthkit_daily_body_fat_pct_2026-10-04", "t": "2026-10-04T00:00:00+02:00", "type": "body_fat_pct", "v": 15.0, "kind": "user_entered"})
        (self.d / "body.json").write_text(json.dumps(body))
        env = envelope()
        env["daily_metrics"]["records"][0]["body_fat_percentage"] = 0.2
        summary, code = apply_batch(self.d, env, lenient=True)
        self.assertEqual(code, 2)
        self.assertIn("never overwritten", summary["conflicts"][0]["reason"])
        self.assertEqual([m["v"] for m in load(self.d, "body.json")["measurements"]], [15.0])


if __name__ == "__main__":
    unittest.main()
