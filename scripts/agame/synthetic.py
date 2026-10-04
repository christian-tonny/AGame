"""Deterministic SYNTHETIC test data (fixture: "synthetic").

Used only by automated tests, Playwright screenshots and the Steve dry run.
It is generic, clearly labelled, and never committed as anyone's records; the UI
shows a "Synthetic test data" banner whenever it is loaded.

  python3 -m agame.synthetic --out /tmp/agame-data --date 2026-10-04 [--days 200] [--missing-last-sleep]
"""

import argparse
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from agame import SCHEMA_VERSION
from agame.empty import empty_payload
from agame.jsonio import atomic_write_json

TZ = timezone(timedelta(hours=2))  # Africa/Kigali has no DST
CENTER = (-1.9536, 30.0606)
SAMPLE_DT = 10  # seconds between workout samples


def _ts(dt):
    return dt.astimezone(TZ).replace(microsecond=0).isoformat()


def _env(domain, as_of):
    p = empty_payload(domain, fixture="synthetic")
    p.update({"generated_at": as_of, "as_of": as_of, "source": "synthetic", "status": "ok", "schema_version": SCHEMA_VERSION})
    return p


# ---------------------------------------------------------------- geometry
def _offset(lat, lon, dx, dy):
    return lat + dy / 111320.0, lon + dx / (111320.0 * math.cos(math.radians(lat)))


def _make_loop(rng, name, cx, cy, radius, wobble, elev_amp, elev_base, n=320):
    pts = []
    phase = rng.random() * math.tau
    for i in range(n + 1):
        a = math.tau * i / n
        r = radius * (1 + wobble * math.sin(3 * a + phase) + 0.5 * wobble * math.cos(5 * a))
        x, y = r * math.cos(a), r * math.sin(a) * 0.7
        lat, lon = _offset(CENTER[0], CENTER[1], cx + x, cy + y)
        ele = elev_base + elev_amp * math.sin(2 * a + phase) + 0.3 * elev_amp * math.sin(7 * a)
        pts.append([round(lon, 6), round(lat, 6), round(ele, 1)])
    return {"name": name, "coords": pts}


def _hav(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _cum(coords):
    out = [0.0]
    for i in range(1, len(coords)):
        out.append(out[-1] + _hav(coords[i - 1], coords[i]))
    return out


def _at(coords, cum, d):
    L = cum[-1]
    d = d % L
    lo, hi = 0, len(cum) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum[mid] <= d:
            lo = mid
        else:
            hi = mid
    seg = cum[hi] - cum[lo] or 1.0
    f = (d - cum[lo]) / seg
    a, b = coords[lo], coords[hi]
    return (a[1] + (b[1] - a[1]) * f, a[0] + (b[0] - a[0]) * f, a[2] + (b[2] - a[2]) * f)


# ---------------------------------------------------------------- generator
class Gen:
    def __init__(self, build_date, days=200, seed=7, missing_last_sleep=False):
        self.rng = random.Random(seed)
        self.end = build_date
        self.start = build_date - timedelta(days=days - 1)
        self.missing_last_sleep = missing_last_sleep
        self.hrmax, self.hrrest = 190, 50
        self.as_of = _ts(datetime.combine(build_date, time(5, 42), tzinfo=TZ))
        rng = self.rng
        self.routes = {
            "rt_lake": _make_loop(rng, "Lake loop", 0, 0, 1300, 0.12, 18, 1480),
            "rt_hill": _make_loop(rng, "Hill repeats loop", 900, -700, 700, 0.2, 35, 1530),
            "rt_ridge": _make_loop(rng, "Ridge road", -1500, 1200, 2600, 0.08, 45, 1500),
        }
        for r in self.routes.values():
            r["cum"] = _cum(r["coords"])
        self.fatigue = 0.0

    # ---- helpers
    def day_dt(self, d, hh, mm=0, ss=0):
        return datetime.combine(d, time(hh, mm, ss), tzinfo=TZ)

    def make_run(self, d, kind, idx):
        rng = self.rng
        rid = {"easy": "rt_lake", "tempo": "rt_lake", "intervals": "rt_hill", "long": "rt_ridge", "test": "rt_lake"}[kind]
        route = self.routes[rid]
        start = self.day_dt(d, 6, 5 + rng.randint(0, 20))
        if kind == "easy":
            dist = rng.uniform(7000, 10500); base_pace = rng.uniform(300, 318)
        elif kind == "tempo":
            dist = rng.uniform(9000, 11000); base_pace = 300
        elif kind == "intervals":
            dist = rng.uniform(8500, 10000); base_pace = 305
        elif kind == "test":
            dist = 5000 + 3000; base_pace = 300
        else:
            dist = rng.uniform(15000, 24000); base_pace = rng.uniform(318, 335)
            start = self.day_dt(d, 6, 30)
        power = rng.random() < 0.5
        t = 0.0; dcur = 0.0; hr = 95.0
        T, HR, DIST, ELE, CAD, PW, LAT, LON = [], [], [], [], [], [], [], []
        laps = []
        prev_ele = None
        lap_start, lap_d = 0.0, 0.0
        while dcur < dist:
            # phase-specific pace / intensity
            frac = dcur / dist
            target_int = 0.68
            pace = base_pace
            if kind == "tempo" and 0.2 < frac < 0.85:
                pace, target_int = 268, 0.87
            elif kind == "intervals" and 0.2 < frac < 0.8:
                cyc = ((dcur - 0.2 * dist) % 1000)
                if cyc < 700:
                    pace, target_int = 238, 0.93
                else:
                    pace, target_int = 330, 0.72
            elif kind == "test" and 1500 < dcur < 6500:
                pace, target_int = 262, 0.92
            elif kind == "long":
                target_int = 0.72 + 0.06 * frac
                pace = base_pace - 8 * frac
            lat, lon, ele = _at(route["coords"], route["cum"], dcur)
            grade = 0.0 if prev_ele is None else (ele - prev_ele) / max(1.0, 3.3)
            prev_ele = ele
            pace = pace * (1 + 3.0 * max(-0.04, min(0.08, grade)))
            pace *= 1 + rng.gauss(0, 0.025)
            speed = 1000.0 / pace
            target_hr = self.hrrest + target_int * (self.hrmax - self.hrrest) + 3 * self.fatigue
            hr += (target_hr - hr) * 0.08 + rng.gauss(0, 0.8) + 0.002 * t / 60
            T.append(round(t)); HR.append(round(min(self.hrmax, hr)))
            DIST.append(round(dcur, 1)); ELE.append(round(ele, 1))
            CAD.append(round(160 + 12 * (speed - 3.0) + rng.gauss(0, 1.5)))
            PW.append(round(70 * speed * 1.04 + rng.gauss(0, 6)) if power else None)
            LAT.append(round(lat, 6)); LON.append(round(lon, 6))
            t += SAMPLE_DT
            dcur += speed * SAMPLE_DT
            if dcur - lap_d >= 1000 or dcur >= dist:
                laps.append({"start_s": lap_start, "end_s": t, "distance_m": round(min(dcur, dist) - lap_d, 1)})
                lap_start, lap_d = t, dcur
        end = start + timedelta(seconds=t)
        gain = sum(max(0, ELE[i] - ELE[i - 1]) for i in range(1, len(ELE)))
        hr_vals = [h for h in HR if h]
        wid = f"syn-run-{d.isoformat()}-{idx}"
        tags = {"long": ["long"], "test": ["test_5k"], "tempo": ["tempo"], "intervals": ["intervals"]}.get(kind, [])
        w = {
            "source_id": wid, "sport": "run", "name": {"easy": "Morning run", "tempo": "Tempo run", "intervals": "Hill intervals",
                                                        "long": "Long run", "test": "5K test"}[kind],
            "start": _ts(start), "end": _ts(end), "duration_s": round(t), "moving_s": round(t),
            "distance_m": round(dist, 1), "elevation_gain_m": round(gain, 1),
            "active_kcal": round(dist / 1000 * 70 * 1.0), "avg_hr": round(sum(hr_vals) / len(hr_vals)), "max_hr": max(hr_vals),
            "avg_cadence": round(sum(CAD) / len(CAD)), "avg_power_w": (round(sum(p for p in PW if p) / len([p for p in PW if p])) if power else None),
            "source": "Synthetic Watch", "device": "Synthetic Watch", "indoor": False, "route_id": rid,
            "samples": {"t": T, "hr": HR, "dist_m": DIST, "elev_m": ELE, "cadence": CAD, "power_w": PW, "lat": LAT, "lon": LON},
            "laps": laps, "segments": None,
            "weather": ({"temp_c": round(rng.uniform(15, 24), 1), "humidity_pct": round(rng.uniform(50, 85)), "wind_kph": round(rng.uniform(2, 15)),
                         "conditions": rng.choice(["Clear", "Cloudy", "Light rain"]), "source": "synthetic"} if rng.random() < 0.7 else None),
            "tags": tags,
        }
        if kind == "intervals":
            w["laps"] = None
        return w

    def make_strength(self, d, idx, with_hr=True):
        rng = self.rng
        start = self.day_dt(d, 17, 30 + rng.randint(0, 20))
        dur = rng.randint(50, 70) * 60
        end = start + timedelta(seconds=dur)
        T, HR = [], []
        hr = 90
        for t in range(0, dur, 30):
            hr += ((118 if (t // 120) % 2 == 0 else 98) - hr) * 0.3 + rng.gauss(0, 2)
            T.append(t); HR.append(round(hr))
        wid = f"syn-str-{d.isoformat()}-{idx}"
        w = {
            "source_id": wid, "sport": "strength", "name": "Strength training", "start": _ts(start), "end": _ts(end),
            "duration_s": dur, "moving_s": None, "distance_m": None, "elevation_gain_m": None, "active_kcal": round(dur / 60 * 6),
            "avg_hr": round(sum(HR) / len(HR)) if with_hr else None, "max_hr": max(HR) if with_hr else None,
            "avg_cadence": None, "avg_power_w": None, "source": "Synthetic Watch", "device": "Synthetic Watch", "indoor": True,
            "route_id": None, "samples": ({"t": T, "hr": HR} if with_hr else None), "laps": None, "segments": None, "weather": None, "tags": [],
        }
        return w

    def strength_log(self, w, day_index, variant):
        rng = self.rng
        prog = day_index / 200.0
        if variant == "lower":
            plan = [("back_squat", 4, 5, 95 + 12 * prog), ("romanian_deadlift", 3, 8, 80 + 8 * prog),
                    ("bulgarian_split_squat", 3, 8, 20 + 4 * prog), ("calf_raise", 3, 12, 60), ("plank", 3, 1, 0)]
        else:
            plan = [("bench_press", 4, 6, 72 + 8 * prog), ("pull_up", 4, 7, 0), ("overhead_press", 3, 8, 45 + 4 * prog),
                    ("db_row", 3, 10, 30 + 4 * prog), ("lateral_raise", 3, 14, 9)]
        exs = []
        for ex_id, sets, reps, wt in plan:
            ss = [{"reps": reps + 2, "weight_kg": round(wt * 0.6 / 2.5) * 2.5 if wt else None, "rpe": None, "rir": None, "warmup": True, "rest_s": 90}]
            for _ in range(sets):
                r = max(1, reps + rng.choice([-1, 0, 0, 1]))
                ss.append({"reps": r, "weight_kg": (round(wt / 2.5) * 2.5) if wt else None,
                           "rpe": round(rng.uniform(7, 9) * 2) / 2, "rir": None, "warmup": False, "rest_s": 150})
            exs.append({"exercise_id": ex_id, "sets": ss, "notes": None, "superset": None})
        return {"id": f"log-{w['source_id']}", "workout_id": w["source_id"], "start": w["start"], "end": w["end"],
                "name": "Lower body" if variant == "lower" else "Upper body", "exercises": exs, "notes": None,
                "kind": "user_entered", "source": "synthetic"}

    def make_sleep(self, d):
        rng = self.rng
        prev = d - timedelta(days=1)
        bed = self.day_dt(prev, 22, 30) + timedelta(minutes=rng.gauss(10, 25))
        wake = self.day_dt(d, 6, 10) + timedelta(minutes=rng.gauss(0, 18))
        segs = [{"stage": "in_bed", "start": _ts(bed), "end": _ts(wake)}]
        t = bed + timedelta(minutes=max(4, rng.gauss(14, 6)))
        segs.append({"stage": "awake", "start": _ts(bed), "end": _ts(t)})
        cycle = 0
        while t < wake - timedelta(minutes=20):
            deep = max(0, rng.gauss(32 - 7 * cycle, 6)); rem = max(5, rng.gauss(12 + 7 * cycle, 4))
            core = max(15, rng.gauss(45, 8))
            for stage, mins in (("core", core * 0.5), ("deep", deep), ("core", core * 0.5), ("rem", rem)):
                if mins <= 0:
                    continue
                e = min(wake, t + timedelta(minutes=mins))
                if e <= t:
                    break
                segs.append({"stage": stage, "start": _ts(t), "end": _ts(e)})
                t = e
            if rng.random() < 0.35 and t < wake - timedelta(minutes=10):
                e = t + timedelta(minutes=rng.randint(2, 9))
                segs.append({"stage": "awake", "start": _ts(t), "end": _ts(e)})
                t = e
            cycle += 1
        if t < wake:
            segs.append({"stage": "core", "start": _ts(t), "end": _ts(wake)})
        return {"source_id": f"syn-sleep-{d.isoformat()}", "date": d.isoformat(), "start": _ts(bed), "end": _ts(wake),
                "source": "Synthetic Watch", "is_nap": False, "segments": segs}

    # ---- main
    def build(self):
        rng = self.rng
        data = {dom: _env(dom, self.as_of) for dom in [
            "profile", "current", "metrics", "sleep", "workouts", "load", "body", "nutrition", "strength", "goals",
            "plans", "routes", "social", "journal", "health_records", "coach"]}
        series = {k: [] for k in ["hrv_sdnn_ms", "resting_hr_bpm", "respiratory_rate_brpm", "steps", "active_energy_kcal",
                                  "resting_energy_kcal", "vo2max_ml_kg_min", "heart_rate_bpm", "walking_hr_bpm", "hr_recovery_bpm",
                                  "spo2_pct", "bp_systolic_mmhg", "bp_diastolic_mmhg", "ground_contact_ms", "vertical_oscillation_cm", "stride_length_m"]}
        workouts, nights, logs, body, meals, water, caffeine, annotations = [], [], [], [], [], [], [], []
        day_i = 0
        vo2 = 50.2
        weight = 84.6
        for d in (self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)):
            wd = d.weekday()
            dayload = 0
            # workouts by schedule: Mon run, Tue/Wed lift, Thu run, Fri rest, weekend optional long run
            todays = []
            if d == self.end:
                pass  # build-date morning: workouts not yet happened
            elif wd == 0:
                todays.append(self.make_run(d, "easy", 0))
            elif wd in (1, 2):
                w = self.make_strength(d, 0)
                todays.append(w)
                if rng.random() < 0.75:
                    logs.append(self.strength_log(w, day_i, "lower" if wd == 1 else "upper"))
            elif wd == 3:
                self.thursdays = getattr(self, "thursdays", 0) + 1
                kind = "test" if self.thursdays % 8 == 4 else rng.choice(["tempo", "intervals"])
                todays.append(self.make_run(d, kind, 0))
            elif wd in (5, 6) and rng.random() < (0.55 if wd == 6 else 0.25):
                todays.append(self.make_run(d, "long" if wd == 6 else "easy", 0))
            for w in todays:
                workouts.append(w)
                dayload += (w["duration_s"] / 60) * (2.0 if w["sport"] == "run" else 1.0)
            self.fatigue = self.fatigue * 0.85 + dayload / 400.0
            # morning metrics (measured the morning of d)
            tm = self.day_dt(d, 5, 30)
            hrv = math.exp(math.log(58) + rng.gauss(0, 0.12) - 0.25 * self.fatigue)
            rhr = 51 + rng.gauss(0, 1.2) + 3 * self.fatigue
            gap = (d.toordinal() % 37 == 11)  # deliberate sync gaps
            if not gap:
                series["hrv_sdnn_ms"].append({"t": _ts(tm), "v": round(hrv, 1), "source_id": f"syn-hrv-{d}", "source": "Synthetic Watch"})
                series["resting_hr_bpm"].append({"date": d.isoformat(), "v": round(rhr, 1), "source_id": f"syn-rhr-{d}", "source": "Synthetic Watch"})
                series["respiratory_rate_brpm"].append({"t": _ts(tm), "v": round(14.6 + rng.gauss(0, 0.4), 1), "source_id": f"syn-rr-{d}"})
                series["spo2_pct"].append({"t": _ts(tm), "v": round(min(100, 97 + rng.gauss(0, 0.8)), 1), "source_id": f"syn-spo2-{d}"})
            if d < self.end:
                series["steps"].append({"date": d.isoformat(), "v": int(max(1500, rng.gauss(9500, 2800) + sum(w.get("distance_m") or 0 for w in todays) * 1.3)),
                                        "source_id": f"syn-steps-{d}"})
                series["active_energy_kcal"].append({"date": d.isoformat(), "v": round(450 + sum(w["active_kcal"] or 0 for w in todays) + rng.gauss(0, 60)),
                                                     "source_id": f"syn-ae-{d}"})
                series["resting_energy_kcal"].append({"date": d.isoformat(), "v": round(1760 + rng.gauss(0, 20)), "source_id": f"syn-re-{d}"})
                series["walking_hr_bpm"].append({"date": d.isoformat(), "v": round(94 + rng.gauss(0, 3) + 2 * self.fatigue, 1), "source_id": f"syn-whr-{d}"})
            for w in todays:
                if w["sport"] == "run":
                    if rng.random() < 0.55:
                        vo2 += rng.gauss(0.03, 0.25)
                        series["vo2max_ml_kg_min"].append({"t": w["end"], "v": round(vo2, 1), "source_id": f"syn-vo2-{w['source_id']}"})
                    series["hr_recovery_bpm"].append({"t": w["end"], "v": round(28 + rng.gauss(0, 3)), "source_id": f"syn-hrr-{w['source_id']}"})
                    series["ground_contact_ms"].append({"t": w["end"], "v": round(238 + rng.gauss(0, 6)), "source_id": f"syn-gct-{w['source_id']}"})
                    series["vertical_oscillation_cm"].append({"t": w["end"], "v": round(8.6 + rng.gauss(0, 0.3), 1), "source_id": f"syn-vo-{w['source_id']}"})
                    series["stride_length_m"].append({"t": w["end"], "v": round(1.18 + rng.gauss(0, 0.04), 2), "source_id": f"syn-sl-{w['source_id']}"})
            if day_i % 9 == 0:
                tb = self.day_dt(d, 7, 0)
                series["bp_systolic_mmhg"].append({"t": _ts(tb), "v": round(118 + rng.gauss(0, 5)), "source_id": f"syn-bps-{d}"})
                series["bp_diastolic_mmhg"].append({"t": _ts(tb), "v": round(76 + rng.gauss(0, 4)), "source_id": f"syn-bpd-{d}"})
            # sleep (wake date d)
            if not gap and not (self.missing_last_sleep and d == self.end):
                nights.append(self.make_sleep(d))
            # body weight trending down
            weight += -0.012 + rng.gauss(0, 0.05)
            if rng.random() < 0.7:
                body.append({"t": _ts(self.day_dt(d, 6, 40)), "type": "weight_kg", "v": round(weight + rng.gauss(0, 0.35), 1),
                             "source_id": f"syn-wt-{d}", "source": "Synthetic Scale", "kind": "observed"})
            if day_i % 14 == 0:
                body.append({"t": _ts(self.day_dt(d, 6, 41)), "type": "body_fat_pct", "v": round(17.5 - day_i * 0.01 + rng.gauss(0, 0.3), 1),
                             "source_id": f"syn-bf-{d}", "source": "Synthetic Scale", "kind": "observed"})
            # nutrition: last 35 days, some days incomplete
            if (self.end - d).days < 35 and d <= self.end:
                plan = [("breakfast", 7, 30, [("Oats with milk", 520, 24, 80, 12, 9, {"whole_grains_g": 60}), ("Eggs", 210, 18, 2, 15, 0, {})]),
                        ("lunch", 12, 45, [("Rice, beans & chicken", 780, 48, 95, 18, 14, {"vegetables_g": 120, "whole_grains_g": 0}), ("Avocado", 160, 2, 9, 15, 7, {"vegetables_g": 80})]),
                        ("snack", 16, 0, [("Greek yogurt", 150, 15, 8, 4, 0, {}), ("Banana", 105, 1, 27, 0, 3, {})]),
                        ("dinner", 19, 30, [("Beef & vegetables", 640, 42, 30, 34, 8, {"vegetables_g": 200, "red_meat_g": 150}), ("Sweet potato", 180, 4, 41, 0, 6, {"vegetables_g": 150})])]
                incomplete = (d == self.end) or (rng.random() < 0.15)
                for mi, (mname, hh, mm, items) in enumerate(plan):
                    if d == self.end and hh > 8:
                        break
                    if incomplete and d != self.end and mi == 3:
                        break
                    its = []
                    for n, kc, p, c, f, fi, fg in items:
                        sc = rng.uniform(0.85, 1.15)
                        its.append({"name": n, "qty": 1, "unit": "serving", "kcal": round(kc * sc), "protein_g": round(p * sc, 1),
                                    "carbs_g": round(c * sc, 1), "fat_g": round(f * sc, 1), "fiber_g": round(fi * sc, 1),
                                    "sugar_g": round(c * 0.15 * sc, 1), "sodium_mg": round(kc * 0.9),
                                    "food_groups": {k: round(v * sc) for k, v in fg.items()} or None, "micros": None})
                    meals.append({"id": f"meal-{d}-{mi}", "t": _ts(self.day_dt(d, hh, mm)), "name": mname.title(), "meal": mname,
                                  "items": its, "source_id": None, "kind": "user_entered"})
                for hh in (8, 11, 15, 18):
                    if d == self.end and hh > 8:
                        break
                    water.append({"t": _ts(self.day_dt(d, hh)), "ml": 500, "source_id": None, "kind": "user_entered"})
                caffeine.append({"t": _ts(self.day_dt(d, 8, 15)), "mg": 95, "source_id": None, "kind": "user_entered"})
                if rng.random() < 0.3 and d != self.end:
                    caffeine.append({"t": _ts(self.day_dt(d, 15, 30)), "mg": 95, "source_id": None, "kind": "user_entered"})
            day_i += 1
        # intraday HR for the last 3 days (stress / energy)
        for back in range(1, 4):
            d = self.end - timedelta(days=back)
            for hh in range(7, 22):
                for mm in range(0, 60, 10):
                    base = 66 + 10 * math.sin(hh / 3.0) + rng.gauss(0, 4)
                    series["heart_rate_bpm"].append({"t": _ts(self.day_dt(d, hh, mm)), "v": round(base), "source_id": f"syn-hr-{d}-{hh}-{mm}"})
        # RPE / feel for recent runs
        for w in workouts[-40:]:
            if w["sport"] == "run" and rng.random() < 0.6:
                annotations.append({"id": f"ann-{w['source_id']}", "workout_id": w["source_id"], "rpe": rng.choice([3, 4, 4, 5, 6, 7, 8]),
                                    "feel": rng.choice([3, 4, 4, 5]), "comment": None, "title": None, "private": False,
                                    "race": False, "tags": [], "created_at": w["end"], "updated_at": w["end"]})

        # ---- assemble files
        p = data["profile"]
        p["athlete"] = {"display_name": "Synthetic Athlete", "sex": "male", "birth_year": 1994, "height_cm": 180}
        p["physiology"] = {
            "hr_max": {"value": 190, "method": "observed_max", "date": "2026-03-14", "kind": "observed", "note": None},
            "hr_rest": None,
            "lthr": {"value": 172, "method": "field_test_30min", "date": "2026-05-02", "kind": "observed", "note": None},
            "threshold_pace_s_per_km": {"value": 268, "method": "field_test_5k", "date": "2026-05-02", "kind": "observed", "note": None},
            "ftp_w": None,
            "sleep_need_base_min": {"value": 465, "method": "configured", "date": "2026-01-01", "kind": "configured", "note": None},
        }
        p["schedule"] = {"template": [
            {"weekday": "monday", "intent": "run", "duration_s": 2700, "type": "AER", "available_from": "06:00", "available_to": "07:30"},
            {"weekday": "tuesday", "intent": "lift", "duration_s": 3600, "type": "STR", "available_from": "17:30", "available_to": "19:00"},
            {"weekday": "wednesday", "intent": "lift", "duration_s": 3600, "type": "STR", "available_from": "17:30", "available_to": "19:00"},
            {"weekday": "thursday", "intent": "run", "duration_s": 3300, "type": "TMP", "available_from": "06:00", "available_to": "07:30"},
            {"weekday": "friday", "intent": "rest", "duration_s": None, "type": "REST", "available_from": None, "available_to": None},
            {"weekday": "saturday", "intent": "optional_run", "duration_s": 3600, "type": "AER", "available_from": "07:00", "available_to": "10:00"},
            {"weekday": "sunday", "intent": "optional_run", "duration_s": 5400, "type": "LR", "available_from": "06:30", "available_to": "10:00"},
        ]}
        p["targets"].update({"protein_g": 150, "kcal": 2600, "carbs_g": 300, "fat_g": 80, "fiber_g": 35, "water_ml": 2500,
                             "caffeine_mg_max": 300, "vegetables_g": 400, "sleep_min": 465, "steps": 9000,
                             "caffeine_cutoff": "14:00", "wake_time": "06:10"})
        start_pt = self.routes["rt_lake"]["coords"][0]
        p["privacy"]["zones"] = [{"id": "pz-home", "label": "Home", "lat": start_pt[1], "lon": start_pt[0], "radius_m": 250}]
        p["ui"]["pinned_charts"] = ["vo2max_ml_kg_min", "hrv_sdnn_ms", "resting_hr_bpm", "weight_kg"]

        data["metrics"]["series"] = series
        data["sleep"]["nights"] = nights
        data["workouts"]["workouts"] = workouts
        data["load"]["annotations"] = annotations
        data["body"]["measurements"] = body
        n = data["nutrition"]
        n.update({"connected": True, "meals": meals, "water": water, "caffeine": caffeine,
                  "recipes": [{"id": "rcp-oats", "name": "Protein oats", "servings": 1, "favorite": True,
                               "items": [{"name": "Oats with milk", "qty": 1, "unit": "serving", "kcal": 520, "protein_g": 24, "carbs_g": 80, "fat_g": 12, "fiber_g": 9}]}],
                  "favorites": [{"name": "Greek yogurt", "qty": 1, "unit": "cup", "kcal": 150, "protein_g": 15, "carbs_g": 8, "fat_g": 4}],
                  "planned_meals": [{"id": "pm-1", "date": (self.end + timedelta(days=1)).isoformat(), "meal": "breakfast", "recipe_id": "rcp-oats", "items": []}],
                  "day_status": [{"date": (self.end - timedelta(days=k)).isoformat(), "complete": True} for k in range(1, 6)]})
        data["strength"].update({"sessions": logs, "routines": [
            {"id": "rtn-lower", "name": "Lower body", "exercises": [{"exercise_id": "back_squat", "sets": 4, "reps": "5", "rpe": 8, "rest_s": 150, "notes": None},
                                                                    {"exercise_id": "romanian_deadlift", "sets": 3, "reps": "8", "rpe": 8, "rest_s": 120, "notes": None}]},
            {"id": "rtn-upper", "name": "Upper body", "exercises": [{"exercise_id": "bench_press", "sets": 4, "reps": "6", "rpe": 8, "rest_s": 150, "notes": None},
                                                                    {"exercise_id": "pull_up", "sets": 4, "reps": "6-8", "rpe": 8, "rest_s": 120, "notes": None}]}],
            "plates": {"bar_kg": 20, "plates_kg": [25, 20, 15, 10, 5, 2.5, 1.25]}})
        data["goals"]["goals"] = [
            {"id": "g-weight", "type": "body_weight", "title": "Body weight", "target": 75, "start_value": 84.6, "unit": "kg",
             "period": {"type": "by_date", "start": self.start.isoformat(), "end": "2027-01-01"}, "direction": "decrease", "status": "active", "kind": "user_entered"},
            {"id": "g-protein", "type": "nutrition", "title": "Protein", "target": 150, "unit": "g", "metric": "protein_g",
             "period": {"type": "week", "start": None, "end": None}, "direction": "increase", "status": "active", "kind": "user_entered"},
            {"id": "g-week-km", "type": "distance", "title": "Weekly running", "target": 30000, "unit": "m", "sport": "run",
             "period": {"type": "week", "start": None, "end": None}, "direction": "increase", "status": "active", "kind": "user_entered"},
            {"id": "g-5k", "type": "record", "title": "5K under 21:30", "target": 1290, "unit": "s", "distance_m": 5000,
             "period": {"type": "by_date", "start": self.start.isoformat(), "end": "2026-12-31"}, "direction": "decrease", "status": "active", "kind": "user_entered"},
            {"id": "g-squat", "type": "strength", "title": "Squat e1RM", "target": 130, "unit": "kg", "exercise_id": "back_squat",
             "period": {"type": "by_date", "start": self.start.isoformat(), "end": "2026-12-31"}, "direction": "increase", "status": "active", "kind": "user_entered"},
            {"id": "g-streak", "type": "streak", "title": "Weekly streak", "target": None, "unit": "weeks",
             "period": {"type": "custom", "start": None, "end": None}, "direction": None, "status": "active", "kind": "user_entered"},
        ]
        race_date = self.end + timedelta(days=56)
        pl = data["plans"]
        week0 = self.end - timedelta(days=self.end.weekday())
        sessions = []
        steps_tempo = [
            {"kind": "warmup", "label": "Warm-up", "duration_s": 900, "target": {"metric": "hr", "low": 130, "high": 145, "zone": None}},
            {"kind": "repeat", "label": None, "repeat": 3, "steps": [
                {"kind": "work", "label": "Tempo", "duration_s": 480, "target": {"metric": "pace", "low": 262, "high": 272, "zone": None}},
                {"kind": "recovery", "label": "Recovery", "duration_s": 120, "target": {"metric": "hr", "low": None, "high": 150, "zone": None}}]},
            {"kind": "cooldown", "label": "Cool-down", "duration_s": 600, "target": {"metric": "open", "low": None, "high": None, "zone": None}},
        ]
        for wk in range(0, 3):
            for wdn, (typ, sport, dur, title) in {0: ("AER", "run", 2700, "Easy run"), 1: ("STR", "strength", 3600, "Lower body"),
                                                   2: ("STR", "strength", 3600, "Upper body"), 3: ("TMP", "run", 3300, "Tempo 3×8 min"),
                                                   6: ("LR", "run", 5400 + wk * 600, "Long run")}.items():
                dd = week0 + timedelta(days=7 * (wk - 1) + wdn)
                sessions.append({"id": f"ps-{dd}", "plan_id": "plan-hm", "date": dd.isoformat(), "type": typ, "sport": sport, "title": title,
                                 "duration_s": dur, "distance_m": None, "load_planned": None,
                                 "steps": steps_tempo if typ == "TMP" else [], "guiding_metric": "pace" if typ == "TMP" else ("hr" if sport == "run" else "rpe"),
                                 "objective": {"AER": "Aerobic base, conversational", "TMP": "Threshold durability", "LR": "Endurance, fuel practice",
                                               "STR": "Strength, RPE 8"}[typ],
                                 "priority": "key" if typ in ("TMP", "LR") else "normal", "template_id": None, "routine_id": None,
                                 "linked_workout_id": None, "status": "planned", "forecast_temp_c": None, "start_time": None, "kind": "user_entered"})
        pl.update({
            "plans": [{"id": "plan-hm", "name": "Half marathon build", "goal": "Half marathon PR", "race_id": "race-hm",
                       "start": (week0 - timedelta(days=7)).isoformat(), "end": race_date.isoformat(), "mode": "race",
                       "phases": [{"name": "Base", "start": (week0 - timedelta(days=7)).isoformat(), "end": (week0 + timedelta(days=13)).isoformat(), "focus": "Aerobic volume"},
                                  {"name": "Build", "start": (week0 + timedelta(days=14)).isoformat(), "end": (race_date - timedelta(days=15)).isoformat(), "focus": "Threshold"},
                                  {"name": "Taper", "start": (race_date - timedelta(days=14)).isoformat(), "end": race_date.isoformat(), "focus": "Freshness"}],
                       "created_by": "synthetic"}],
            "sessions": sessions,
            "templates": [{"id": "tpl-tempo", "name": "Tempo 3×8 min", "type": "TMP", "sport": "run", "duration_s": 3300, "distance_m": None,
                           "steps": steps_tempo, "guiding_metric": "pace"}],
            "races": [{"id": "race-hm", "name": "City Half Marathon", "date": race_date.isoformat(), "distance_m": 21097.5, "priority": "A",
                       "goal_time_s": 5700, "location": None},
                      {"id": "race-10k", "name": "Club 10K", "date": (self.end + timedelta(days=27)).isoformat(), "distance_m": 10000, "priority": "C",
                       "goal_time_s": None, "location": None}],
            "calendar": [{"id": "cal-1", "title": "Team offsite", "start": _ts(self.day_dt(self.end + timedelta(days=(3 - self.end.weekday()) % 7), 6, 30)),
                          "end": _ts(self.day_dt(self.end + timedelta(days=(3 - self.end.weekday()) % 7), 9, 0)), "source": "synthetic", "busy": True}],
            "routines": [{"id": "rtn-tempo", "name": "Tempo 3×8 min", "sport": "run", "steps": steps_tempo, "guiding_metric": "pace", "notes": None}],
            "prehab": [{"id": "ph-1", "name": "Runner's hips & calves", "focus": "Hips, calves", "duration_min": 12,
                        "exercises": ["clamshell", "copenhagen_plank", "calf_raise", "tibialis_raise"]}],
            "prehab_log": [{"id": f"phl-{k}", "date": (self.end - timedelta(days=k * 3 + 1)).isoformat(), "routine_id": "ph-1"} for k in range(6)],
            "mode": "race",
        })
        feats = []
        for rid, r in self.routes.items():
            feats.append({"type": "Feature", "id": rid, "properties": {
                "id": rid, "kind": "route", "name": r["name"], "workout_id": None, "sport": "run", "favorite": rid == "rt_lake",
                "offline": rid == "rt_lake", "surface": {"paved_pct": 70 if rid != "rt_ridge" else 40, "unpaved_pct": 25 if rid != "rt_ridge" else 55, "unknown_pct": 5},
                "difficulty": {"rt_lake": "easy", "rt_hill": "hard", "rt_ridge": "moderate"}[rid], "source": "synthetic", "created_at": None, "kind_detail": None},
                "geometry": {"type": "LineString", "coordinates": r["coords"]}})
        seg = self.routes["rt_hill"]["coords"][60:110]
        feats.append({"type": "Feature", "id": "seg-hill", "properties": {"id": "seg-hill", "kind": "segment", "name": "Hill climb", "workout_id": None,
                      "sport": "run", "favorite": False, "offline": False, "surface": None, "difficulty": None, "source": "synthetic", "created_at": None, "kind_detail": None},
                      "geometry": {"type": "LineString", "coordinates": seg}})
        data["routes"]["features"] = feats
        j = data["journal"]
        j["habits"] = [{"id": "h-stretch", "name": "Stretching", "unit": None, "boolean": True}]
        j["entries"] = []
        for k in range(1, 40):
            dd = self.end - timedelta(days=k)
            j["entries"].append({"id": f"j-mood-{k}", "date": dd.isoformat(), "t": None, "type": "mood", "value": rng.choice([3, 4, 4, 5]), "unit": "1-5",
                                 "text": None, "habit_id": None, "kind": "user_entered"})
            if rng.random() < 0.5:
                j["entries"].append({"id": f"j-h-{k}", "date": dd.isoformat(), "t": None, "type": "habit", "value": 1, "unit": None, "text": None,
                                     "habit_id": "h-stretch", "kind": "user_entered"})
            if rng.random() < 0.25:
                j["entries"].append({"id": f"j-al-{k}", "date": dd.isoformat(), "t": None, "type": "alcohol", "value": rng.choice([1, 2]), "unit": "drinks",
                                     "text": None, "habit_id": None, "kind": "user_entered"})
        j["status"] = [{"id": "st-1", "status": "traveling", "start": (self.end - timedelta(days=33)).isoformat(),
                        "end": (self.end - timedelta(days=30)).isoformat(), "source": "user", "note": None}]
        data["health_records"]["records"] = [{"id": "lab-1", "date": (self.end - timedelta(days=60)).isoformat(), "type": "lab", "title": "Annual bloodwork",
                                              "provider": "Synthetic Lab", "file": None, "text": None, "kind": "user_entered",
                                              "biomarkers": [{"name": "Glucose (fasting)", "code": "glucose", "value": 5.0, "unit": "mmol/L", "ref_low": 3.9, "ref_high": 5.6, "ref_text": None},
                                                             {"name": "Albumin", "code": "albumin", "value": 46, "unit": "g/L", "ref_low": 35, "ref_high": 50, "ref_text": None},
                                                             {"name": "Creatinine", "code": "creatinine", "value": 88, "unit": "umol/L", "ref_low": 60, "ref_high": 110, "ref_text": None},
                                                             {"name": "Ferritin", "code": "ferritin", "value": 95, "unit": "ug/L", "ref_low": 30, "ref_high": 400, "ref_text": None}]}]
        data["coach"].update({
            "memory": [{"id": "m-1", "type": "preference", "text": "Prefers morning runs before 07:30", "created_at": self.as_of, "updated_at": self.as_of, "spec": None},
                       {"id": "m-2", "type": "goal", "text": "Half marathon PR this season", "created_at": self.as_of, "updated_at": self.as_of, "spec": None}],
            "checkins": [{"id": "ci-morning", "type": "morning_report", "time": "05:55", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "text": None, "enabled": True},
                         {"id": "ci-creatine", "type": "reminder", "time": "15:00", "days": ["mon", "tue", "wed", "thu", "fri"], "text": "Creatine 5 g", "enabled": True},
                         {"id": "ci-weekly", "type": "weekly_summary", "time": "19:00", "days": ["sun"], "text": None, "enabled": True}],
            "threads": [], "last_maintenance": self.as_of})
        doms = {}
        for dom in ["metrics", "sleep", "workouts", "body", "nutrition", "strength"]:
            doms[dom] = {"last_sync": self.as_of, "last_sample": self.as_of, "expected_for": self.end.isoformat(), "received": True, "status": "ok", "note": None}
        if self.missing_last_sleep:
            doms["sleep"].update({"received": False, "status": "missing", "note": "Sleep not synced yet"})
        data["current"].update({"domains": doms, "imports": []})
        if self.missing_last_sleep:
            data["sleep"]["status"] = "partial"
        return data


def write_synthetic(out_dir, build_date, days=200, seed=7, missing_last_sleep=False):
    data = Gen(build_date, days=days, seed=seed, missing_last_sleep=missing_last_sleep).build()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for dom, payload in data.items():
        fname = "routes.geojson" if dom == "routes" else f"{dom}.json"
        atomic_write_json(out / fname, payload, indent=None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default="2026-10-04")
    ap.add_argument("--days", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--missing-last-sleep", action="store_true")
    a = ap.parse_args()
    write_synthetic(a.out, date.fromisoformat(a.date), a.days, a.seed, a.missing_last_sleep)
    print(f"synthetic data written to {a.out}")


if __name__ == "__main__":
    main()
