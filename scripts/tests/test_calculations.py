"""Calculation units: load, zones, recovery, weight, best efforts, privacy, time zones, PhenoAge."""

import copy
import math
import unittest
from datetime import date, timedelta
from types import SimpleNamespace

from helpers import _TMP, BUILD_DATE, snapshot, synthetic_dir

from agame import timeutil as tu
from agame.compute import activity, body, load, privacy, recovery
from agame.compute.ctx import Ctx
from agame.compute.extras import phenoage
from agame.datastore import load_all
from agame.paths import load_config

K = (0.64, 1.92)


def ctx_from(data, d=BUILD_DATE):
    return Ctx(copy.deepcopy(data), d)


class Trimp(unittest.TestCase):
    def test_steady_stream_equals_average_formula(self):
        pts = [(t, 150) for t in range(0, 3601, 5)]
        a = load.trimp_from_stream(pts, 190, 50, K)
        b = load.trimp_from_avg(150, 60, 190, 50, K)
        self.assertAlmostEqual(a, b, places=6)

    def test_zero_at_rest_and_monotonic(self):
        self.assertEqual(load.trimp_from_avg(50, 60, 190, 50, K), 0)
        vals = [load.trimp_from_avg(hr, 60, 190, 50, K) for hr in (100, 130, 160, 185)]
        self.assertEqual(vals, sorted(vals))

    def test_banister_value(self):
        hrr = (150 - 50) / (190 - 50)
        self.assertAlmostEqual(load.trimp_from_avg(150, 60, 190, 50, K), 60 * hrr * 0.64 * math.exp(1.92 * hrr), places=9)

    def test_long_gaps_are_capped(self):
        pts = [(0, 150), (5, 150), (10, 150), (3600, 150)]  # watch paused for an hour
        self.assertLess(load.trimp_from_stream(pts, 190, 50, K), load.trimp_from_avg(150, 5, 190, 50, K))


class Pmc(unittest.TestCase):
    def test_ewma_and_form_definition(self):
        snap, ctx = snapshot()
        cfg = load_config(ctx.profile)["load"]
        series = snap["training"]["pmc"]["series"]
        ctl = atl = 0.0
        for row in series:
            tsb = ctl - atl
            ctl += (row["load"] - ctl) / cfg["ctl_days"]
            atl += (row["load"] - atl) / cfg["atl_days"]
            self.assertAlmostEqual(row["ctl"], round(ctl, 2), delta=0.02)
            self.assertAlmostEqual(row["atl"], round(atl, 2), delta=0.02)
            self.assertAlmostEqual(row["tsb"], round(tsb, 2), delta=0.03)

    def test_empty_is_missing(self):
        snap, _ = snapshot("empty")
        self.assertEqual(snap["training"]["pmc"]["series"], [])
        self.assertIsNone(snap["today"]["load"]["tsb"]["v"])


class Zones(unittest.TestCase):
    def setUp(self):
        self.data, _, _ = load_all(synthetic_dir())

    def test_five_zone_from_hr_max(self):
        z = load.hr_zones(ctx_from(self.data))
        self.assertEqual(z["basis"], "hr_max")
        self.assertEqual(len(z["zones"]), 5)
        self.assertEqual(z["zones"][0]["low"], 0)
        lows = [x["low"] for x in z["zones"]]
        self.assertEqual(lows, sorted(lows))
        self.assertLessEqual(z["zones"][-1]["high"], 190)

    def test_no_age_based_guess(self):
        d = copy.deepcopy(self.data)
        d["profile"]["physiology"]["hr_max"] = None
        d["profile"]["athlete"]["birth_year"] = 1990
        z = load.hr_zones(ctx_from(d))
        self.assertIsNone(z["zones"])
        self.assertEqual(z["status"], "missing")

    def test_seven_zone_needs_lthr(self):
        d = copy.deepcopy(self.data)
        d["profile"]["zones"] = {"model": "7zone", "hr_custom_bpm": None, "pace_custom_s_per_km": None}
        z = load.hr_zones(ctx_from(d))
        self.assertEqual((z["basis"], len(z["zones"])), ("lthr", 7))
        d["profile"]["physiology"]["lthr"] = None
        self.assertIsNone(load.hr_zones(ctx_from(d))["zones"])

    def test_time_in_zones_sums_to_duration(self):
        zones = [{"low": 0}, {"low": 120}, {"low": 150}]
        secs = load.time_in_zones([(t, 100 if t < 600 else 160) for t in range(0, 1201)], zones)
        self.assertAlmostEqual(sum(secs), 1200)
        self.assertGreater(secs[0], 590)
        self.assertGreater(secs[2], 590)


class Recovery(unittest.TestCase):
    def test_missing_inputs_give_no_score(self):
        data, _, _ = load_all(synthetic_dir())
        d = copy.deepcopy(data)
        day = BUILD_DATE.isoformat()
        for sid in ("resting_hr_bpm", "hrv_sdnn_ms"):
            d["metrics"]["series"][sid] = [p for p in d["metrics"]["series"][sid] if (p.get("date") or p.get("t", ""))[:10] != day]
        self.assertIsNone(recovery.recovery_for(ctx_from(d), BUILD_DATE))

    def test_score_has_components_and_range(self):
        snap, ctx = snapshot()
        r = recovery.recovery_for(ctx, BUILD_DATE)
        self.assertIsNotNone(r)
        self.assertTrue(0 <= r["score"] <= 100)
        self.assertIn("hrv", r["components"])
        self.assertAlmostEqual(sum(c["weight"] for c in r["components"].values()), 1.0, places=2)

    def test_missing_sleep_lowers_coverage_not_invents(self):
        from agame.synthetic import write_synthetic
        import tempfile
        out = write_synthetic(tempfile.mkdtemp(dir=_TMP), BUILD_DATE, missing_last_sleep=True)
        data, _, _ = load_all(out)
        r = recovery.recovery_for(ctx_from(data), BUILD_DATE)
        self.assertNotIn("sleep_debt", r["components"])
        self.assertTrue(any(m["id"] == "sleep_debt" for m in r["missing"]))


class Weight(unittest.TestCase):
    cfg = load_config()["body"]
    ctx = SimpleNamespace(d=date(2026, 10, 4))
    goal = {"target": 75, "period": {"end": "2027-01-03"}, "start_value": 85}

    def test_on_track_and_projection(self):
        # 13 weeks left, 8 kg to lose -> ~0.615 kg/week required
        t = body.trajectory(self.ctx, self.goal, 83, -0.65, self.cfg)
        self.assertAlmostEqual(t["required_kg_per_week"], -8 / 13, places=2)
        self.assertIn(t["status"], ("on_track", "ahead"))
        self.assertEqual(t["progress_pct"], 20.0)
        self.assertIsNotNone(t["projected_date"])

    def test_behind_when_slope_too_small_or_wrong_way(self):
        self.assertEqual(body.trajectory(self.ctx, self.goal, 83, -0.2, self.cfg)["status"], "behind")
        t = body.trajectory(self.ctx, self.goal, 83, 0.3, self.cfg)
        self.assertEqual(t["status"], "behind")
        self.assertIsNone(t["projected_date"])

    def test_insufficient_without_trend(self):
        self.assertEqual(body.trajectory(self.ctx, self.goal, 83, None, self.cfg)["status"], "insufficient")


class BestEfforts(unittest.TestCase):
    def test_constant_speed(self):
        t = list(range(0, 751))
        dist = [4.0 * x for x in t]
        self.assertAlmostEqual(activity.best_effort_time(t, dist, 1000), 250, places=6)

    def test_finds_fast_middle(self):
        t, dist, x = [], [], 0.0
        for s in range(0, 1200):
            t.append(s)
            dist.append(x)
            x += 5.0 if 400 <= s < 600 else 3.0
        self.assertAlmostEqual(activity.best_effort_time(t, dist, 1000), 200, places=6)

    def test_too_short(self):
        self.assertIsNone(activity.best_effort_time([0, 100], [0, 500], 1000))

    def test_records_are_sorted_and_plausible(self):
        snap, _ = snapshot()
        for row in snap["records"]["run"]:
            times = [x["time_s"] for x in row["top"]]
            self.assertEqual(times, sorted(times))
            self.assertGreater(row["distance_m"] / row["best"]["time_s"], 2.0)
            self.assertLess(row["distance_m"] / row["best"]["time_s"], 7.0)

    def test_splits_cover_the_run(self):
        snap, _ = snapshot()
        det = next(d for d in snap["activities"]["details"].values() if d["splits"])
        total = sum(s["distance_m"] for s in det["splits"])
        self.assertAlmostEqual(total, det["row"]["distance_m"], delta=det["row"]["distance_m"] * 0.02)
        self.assertGreaterEqual(det["matched"]["count"], 1)


class Privacy(unittest.TestCase):
    line = [(-1.95, 30.05 + i * 0.0001) for i in range(300)]  # ~11 m apart, ~3.3 km

    def test_start_and_end_trimmed(self):
        out = privacy.apply(self.line, {"zones": [], "hide_start_end_m": 200})
        self.assertEqual(len(out), 1)
        first = out[0][0]
        self.assertGreaterEqual(privacy.haversine_m(*self.line[0], *first), 199)
        self.assertGreaterEqual(privacy.haversine_m(*self.line[-1], *out[0][-1]), 199)

    def test_zone_removes_points(self):
        mid = self.line[150]
        out = privacy.apply(self.line, {"zones": [{"lat": mid[0], "lon": mid[1], "radius_m": 100}], "hide_start_end_m": 0})
        self.assertEqual(len(out), 2)
        for ln in out:
            for p in ln:
                self.assertGreater(privacy.haversine_m(p[0], p[1], *mid), 100)

    def test_html_never_contains_zone_centre(self):
        snap, ctx = snapshot()
        zone = ctx.profile["privacy"]["zones"][0]
        pts = list(_coords({k: v for k, v in snap.items() if k != "profile"}))
        self.assertGreater(len(pts), 1000)
        for lat, lon in pts:
            self.assertGreater(privacy.haversine_m(lat, lon, zone["lat"], zone["lon"]), zone["radius_m"] - 1)
        for z in snap["profile"]["privacy"]["zones"]:
            self.assertFalse({"lat", "lon"} & set(z), "zone centres must not be embedded")


def _coords(obj):
    """Every [lat, lon] pair inside map/route/heatmap structures of the snapshot."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _coords(v)
    elif isinstance(obj, list):
        if len(obj) >= 2 and all(isinstance(x, (int, float)) for x in obj[:2]) and -90 <= obj[0] <= 90 and 29 < obj[1] < 31.5 and -3 < obj[0] < -1:
            yield obj[0], obj[1]
        else:
            for v in obj:
                yield from _coords(v)


class TimeZones(unittest.TestCase):
    def test_utc_evening_is_next_local_day(self):
        tz = tu.tzinfo("Africa/Kigali")
        self.assertEqual(tu.local_date("2026-10-03T23:30:00+00:00", tz), date(2026, 10, 4))
        self.assertEqual(tu.local_date("2026-10-03T21:59:59+00:00", tz), date(2026, 10, 3))

    def test_naive_rejected(self):
        with self.assertRaises(ValueError):
            tu.parse_ts("2026-10-03T23:30:00")

    def test_workout_assigned_to_local_day(self):
        data, _, _ = load_all(synthetic_dir())
        d = copy.deepcopy(data)
        w = copy.deepcopy(next(x for x in d["workouts"]["workouts"] if x["sport"] == "strength"))
        w.update(source_id="tz-test", start="2026-10-03T22:30:00+00:00", end="2026-10-03T23:10:00+00:00", route_id=None)
        w.pop("samples", None)
        d["workouts"]["workouts"].append(w)
        ctx = ctx_from(d)
        self.assertIn("tz-test", [x["source_id"] for x in ctx.workouts_by_day[date(2026, 10, 4)]])

    def test_week_start(self):
        self.assertEqual(tu.week_start(date(2026, 10, 4)), date(2026, 9, 28))


class PhenoAge(unittest.TestCase):
    base = {"albumin": 45, "creatinine": 80, "glucose": 5.0, "crp": 0.1, "lymphocyte_pct": 30, "mcv": 90, "rdw": 13,
            "alp": 70, "wbc": 6}

    def test_healthy_markers_near_chronological_age(self):
        self.assertTrue(25 < phenoage(40, self.base) < 50)

    def test_worse_markers_raise_age(self):
        worse = dict(self.base, crp=1.5, rdw=15, glucose=7)
        self.assertGreater(phenoage(40, worse), phenoage(40, self.base) + 3)

    def test_older_is_older(self):
        self.assertGreater(phenoage(60, self.base), phenoage(40, self.base))


if __name__ == "__main__":
    unittest.main()
