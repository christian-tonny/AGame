"""Apple Health export backfill: streaming parse, per-device totals, sleep stages, workouts with HR and routes, idempotency, no duplicates with Muse."""

import io
import json
import zipfile
import unittest
from datetime import datetime, timedelta

from helpers import empty_dir

from agame.apple_export import ExportError, run
from agame.importer import apply_batch

T = "%Y-%m-%d %H:%M:%S +0200"


def ts(dt):
    return dt.strftime(T)


def rec(typ, start, value, unit, source="Apple Watch", end=None):
    return (f'<Record type="{typ}" sourceName="{source}" unit="{unit}" creationDate="{ts(start)}" startDate="{ts(start)}" '
            f'endDate="{ts(end or start)}" value="{value}"/>')


def make_export(path, entity=False):
    d = datetime(2026, 9, 20)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<!DOCTYPE HealthData [\n<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>\n' + ('<!ENTITY x "boom">\n' if entity else '') + ']>',
             '<HealthData locale="en_US">', f'<ExportDate value="{ts(datetime(2026, 10, 3, 9, 0))}"/>', '<Me/>']
    lines += [rec("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", d.replace(hour=3), 40, "ms"),
              rec("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", d.replace(hour=15), 30, "ms"),
              rec("HKQuantityTypeIdentifierRestingHeartRate", d.replace(hour=8), 55, "count/min"),
              rec("HKQuantityTypeIdentifierStepCount", d.replace(hour=10), 5000, "count", "iPhone"),
              rec("HKQuantityTypeIdentifierStepCount", d.replace(hour=10), 6000, "count", "Apple Watch"),
              rec("HKQuantityTypeIdentifierDietarySodium", d.replace(hour=12), 900, "mg", "MyFood"),
              rec("HKQuantityTypeIdentifierOxygenSaturation", d.replace(hour=4), 0.97, "%")]
    night = d.replace(hour=23) - timedelta(days=1)
    for i, st in enumerate(["AsleepCore", "AsleepDeep", "AsleepREM", "AsleepCore"]):
        a = night + timedelta(minutes=90 * i)
        lines.append(f'<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="{ts(a)}" endDate="{ts(a + timedelta(minutes=90))}" value="HKCategoryValueSleepAnalysis{st}"/>')
    lines.append(f'<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="iPhone" startDate="{ts(night)}" endDate="{ts(night + timedelta(hours=6))}" value="HKCategoryValueSleepAnalysisInBed"/>')
    w0 = d.replace(hour=6)
    for k in range(0, 1800, 10):
        lines.append(rec("HKQuantityTypeIdentifierHeartRate", w0 + timedelta(seconds=k), 140 + (k % 60) // 10, "count/min"))
    lines.append(f'<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30" durationUnit="min" sourceName="Apple Watch" '
                 f'startDate="{ts(w0)}" endDate="{ts(w0 + timedelta(minutes=30))}">'
                 '<MetadataEntry key="HKIndoorWorkout" value="0"/><MetadataEntry key="HKWeatherTemperature" value="68 degF"/>'
                 '<MetadataEntry key="HKWeatherHumidity" value="6500 %"/><MetadataEntry key="HKElevationAscended" value="4200 cm"/>'
                 '<WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="x" endDate="x" average="145" minimum="120" maximum="165" unit="count/min"/>'
                 '<WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" startDate="x" endDate="x" sum="5.4" unit="km"/>'
                 '<WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" startDate="x" endDate="x" sum="380" unit="kcal"/>'
                 '<WorkoutRoute sourceName="Apple Watch"><FileReference path="/workout-routes/route_1.gpx"/></WorkoutRoute></Workout>')
    lines.append('</HealthData>')
    gpx = ['<?xml version="1.0"?><gpx><trk><trkseg>']
    for k in range(0, 1800, 2):
        t = (w0 - timedelta(hours=2) + timedelta(seconds=k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        gpx.append(f'<trkpt lat="{-1.95 + k * 0.00001:.6f}" lon="{30.06 + k * 0.00001:.6f}"><ele>{1500 + k % 20}</ele><time>{t}</time></trkpt>')
    gpx.append('</trkseg></trk></gpx>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("apple_health_export/export.xml", "\n".join(lines))
        z.writestr("apple_health_export/workout-routes/route_1.gpx", "".join(gpx))
    return path


class AppleExport(unittest.TestCase):
    def setUp(self):
        self.d = empty_dir()
        self.zip = make_export(self.d / "export.zip")

    def load(self, f):
        return json.loads((self.d / f).read_text())

    def test_backfill_then_rerun_and_muse_overlap(self):
        summary, code = run(self.zip, self.d, "Africa/Kigali")
        self.assertIn(code, (0, 2), summary)
        m = self.load("metrics.json")["series"]
        self.assertEqual([p["v"] for p in m["steps"]], [6000.0])  # largest single device, never iPhone + Watch
        self.assertEqual([p["v"] for p in m["hrv_sdnn_ms"]], [35.0])  # daily average, like Muse's series
        self.assertEqual(m["steps"][0]["source_id"], "healthkit_daily_steps_2026-09-20")
        self.assertAlmostEqual(m["spo2_pct"][0]["v"], 97.0)
        nut = self.load("nutrition.json")["daily_totals"][0]
        self.assertAlmostEqual(nut["sodium_mg"], 900.0)
        nights = self.load("sleep.json")["nights"]
        self.assertEqual(len(nights), 1)
        self.assertEqual({s["stage"] for s in nights[0]["segments"]}, {"core", "deep", "rem"})  # the Watch night, not the iPhone in-bed block
        w = self.load("workouts.json")["workouts"][0]
        self.assertEqual(w["sport"], "run")
        self.assertTrue(w["source_id"].startswith("healthkit_"))
        self.assertGreater(len(w["samples"]["t"]), 100)
        self.assertTrue(any(v is not None for v in w["samples"]["hr"]))
        self.assertTrue(any(v is not None for v in w["samples"]["lat"]))
        self.assertAlmostEqual(w["weather"]["temp_c"], 20.0, places=0)
        self.assertEqual(w["weather"]["humidity_pct"], 65)
        before = {f: (self.d / f).read_bytes() for f in ("metrics.json", "sleep.json", "workouts.json")}
        summary, code = run(self.zip, self.d, "Africa/Kigali")
        self.assertEqual(summary["status"], "already_imported")
        self.assertEqual({f: (self.d / f).read_bytes() for f in before}, before)
        # Muse's summaries of the same night and run (its own UUIDs) are recognised, not added twice
        env = {"format": "muse.v1", "generated_at": "2026-10-03T10:00:00+02:00", "timezone": "Africa/Kigali",
               "sleep": {"records": [{"id": "healthkit_MUSE-NIGHT", "start_datetime": nights[0]["start"][:19].replace("T", " "),
                                      "end_datetime": nights[0]["end"][:19].replace("T", " "), "sleep_core_duration_sec": 10800.0}]},
               "workouts": {"records": [{"id": "healthkit_MUSE-RUN", "workout_type": "running", "start_datetime": "2026-09-20 06:00:05",
                                         "end_datetime": "2026-09-20 06:29:58", "hr_average_bpm": 145.0}]}}
        summary, code = apply_batch(self.d, env, lenient=True)
        self.assertEqual(sorted(x["source_id"] for x in summary["duplicates"]), ["healthkit_MUSE-NIGHT", "healthkit_MUSE-RUN"])
        self.assertEqual(len(self.load("sleep.json")["nights"]), 1)
        self.assertEqual(len(self.load("workouts.json")["workouts"]), 1)

    def test_entity_declarations_are_refused(self):
        bad = make_export(self.d / "bad.zip", entity=True)
        with self.assertRaises(ExportError):
            run(bad, self.d, "Africa/Kigali")


if __name__ == "__main__":
    unittest.main()
