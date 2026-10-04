"""muse.v1 adapter: Muse's untouched Apple Health query results -> an AGame HealthKit batch (batch_version 2).

Envelope:
  {"format": "muse.v1", "generated_at": "<ISO with offset>", "timezone": "Africa/Kigali",
   "sleep": {"coverage": {...}, "records": [...]}, "workouts": {"coverage": {...}, "records": [...]},
   "daily_metrics": {"coverage": {...}, "records": [...]}}

Every number goes through UNITS: the unit Muse sends, the plausible range of that raw value, and how it is stored.
A value outside its range is rejected with a reason. It is never rescaled on a guess. Absent keys stay missing.
Fixtures with real Muse records: scripts/tests/fixtures/muse-*.json.
"""

from datetime import datetime, timezone

from agame import timeutil as tu

FORMAT = "muse.v1"

# field -> (target, input unit, plausible raw range, factor to stored unit, stored unit)
# target: "metric:<series>", "body:<type>", "nutrition:<field>", "micro:<key>"
UNITS = {
    # recovery and vitals
    "heart_rate_variability_ms": ("metric:hrv_sdnn_ms", "ms (daily average SDNN)", (5, 300), 1, "ms"),
    "resting_hr_average_bpm": ("metric:resting_hr_bpm", "bpm", (25, 150), 1, "bpm"),
    "respiratory_rate_average": ("metric:respiratory_rate_brpm", "breaths/min", (4, 60), 1, "br/min"),
    "oxygen_saturation_average": ("metric:spo2_pct", "fraction 0-1", (0.5, 1.0), 100, "%"),
    "apple_sleeping_wrist_temperature_average": ("metric:wrist_temp_c", "°C (absolute)", (30, 42), 1, "°C"),
    "vo2_max": ("metric:vo2max_ml_kg_min", "ml/kg/min", (10, 95), 1, "ml/kg/min"),
    "heart_rate_recovery_one_minute_average": ("metric:hr_recovery_bpm", "bpm", (1, 120), 1, "bpm"),
    "walking_heart_rate_average_average": ("metric:walking_hr_bpm", "bpm", (40, 200), 1, "bpm"),
    # activity
    "step_count": ("metric:steps", "count", (0, 150000), 1, "steps"),
    "active_energy_burned_kcal": ("metric:active_energy_kcal", "kcal", (0, 15000), 1, "kcal"),
    "basal_energy_burned_kcal": ("metric:resting_energy_kcal", "kcal", (300, 6000), 1, "kcal"),
    "distance_walking_running_meters": ("metric:distance_walk_run_m", "m", (0, 300000), 1, "m"),
    "apple_stand_time_sum": ("metric:stand_min", "min", (0, 1440), 1, "min"),
    "apple_exercise_time_sum": ("metric:exercise_min", "min", (0, 1440), 1, "min"),
    # running and walking form
    "running_ground_contact_time_average": ("metric:ground_contact_ms", "ms", (100, 600), 1, "ms"),
    "running_stride_length_average": ("metric:stride_length_m", "m", (0.3, 3.0), 1, "m"),
    "running_vertical_oscillation_average": ("metric:vertical_oscillation_cm", "m", (0.02, 0.3), 100, "cm"),
    "running_power_average": ("metric:running_power_w", "W", (20, 1000), 1, "W"),
    "walking_speed_average": ("metric:walking_speed_mps", "m/s", (0.1, 3.0), 1, "m/s"),
    "walking_asymmetry_percentage_average": ("metric:walking_asymmetry_pct", "fraction 0-1", (0, 1), 100, "%"),
    "walking_double_support_percentage_average": ("metric:walking_double_support_pct", "fraction 0-1", (0, 1), 100, "%"),
    # not observed yet: mapped so they turn on without code changes when Muse starts sending them
    "blood_pressure_systolic_average": ("metric:bp_systolic_mmhg", "mmHg", (60, 260), 1, "mmHg"),
    "blood_pressure_diastolic_average": ("metric:bp_diastolic_mmhg", "mmHg", (30, 160), 1, "mmHg"),
    "blood_glucose_average": ("metric:glucose_mg_dl", "mg/dL", (30, 600), 1, "mg/dL"),
    "body_mass_average": ("body:weight_kg", "kg", (30, 300), 1, "kg"),
    "body_fat_percentage": ("body:body_fat_pct", "fraction 0-1", (0.03, 0.7), 100, "%"),
    "lean_body_mass_average": ("body:lean_mass_kg", "kg", (20, 150), 1, "kg"),
    "waist_circumference_average": ("body:waist_cm", "m", (0.4, 2.0), 100, "cm"),
    "bmi": ("body:bmi", "kg/m²", (10, 70), 1, "kg/m²"),
    # nutrition day totals (every dietary_* field except energy and water is in grams)
    "dietary_energy_sum": ("nutrition:kcal", "kcal", (0, 15000), 1, "kcal"),
    "dietary_protein_sum": ("nutrition:protein_g", "g", (0, 600), 1, "g"),
    "dietary_carbs_sum": ("nutrition:carbs_g", "g", (0, 1500), 1, "g"),
    "dietary_fat_sum": ("nutrition:fat_g", "g", (0, 600), 1, "g"),
    "dietary_fiber_sum": ("nutrition:fiber_g", "g", (0, 200), 1, "g"),
    "dietary_sugar_sum": ("nutrition:sugar_g", "g", (0, 1000), 1, "g"),
    "dietary_sodium_sum": ("nutrition:sodium_mg", "g", (0, 30), 1000, "mg"),
    "dietary_water_sum": ("nutrition:water_ml", "mL", (0, 20000), 1, "mL"),
    "dietary_fat_saturated_sum": ("micro:fat_saturated_g", "g", (0, 300), 1, "g"),
    "dietary_fat_monounsaturated_sum": ("micro:fat_monounsaturated_g", "g", (0, 300), 1, "g"),
    "dietary_fat_polyunsaturated_sum": ("micro:fat_polyunsaturated_g", "g", (0, 300), 1, "g"),
    "dietary_cholesterol_sum": ("micro:cholesterol_mg", "g", (0, 5), 1000, "mg"),
    "dietary_potassium_sum": ("micro:potassium_mg", "g", (0, 20), 1000, "mg"),
    "dietary_calcium_sum": ("micro:calcium_mg", "g", (0, 10), 1000, "mg"),
    "dietary_magnesium_sum": ("micro:magnesium_mg", "g", (0, 5), 1000, "mg"),
    "dietary_phosphorus_sum": ("micro:phosphorus_mg", "g", (0, 10), 1000, "mg"),
    "dietary_iron_sum": ("micro:iron_mg", "g", (0, 1), 1000, "mg"),
    "dietary_zinc_sum": ("micro:zinc_mg", "g", (0, 1), 1000, "mg"),
    "dietary_copper_sum": ("micro:copper_mg", "g", (0, 0.1), 1000, "mg"),
    "dietary_manganese_sum": ("micro:manganese_mg", "g", (0, 0.1), 1000, "mg"),
    "dietary_niacin_sum": ("micro:niacin_mg", "g", (0, 1), 1000, "mg"),
    "dietary_thiamin_sum": ("micro:thiamin_mg", "g", (0, 0.5), 1000, "mg"),
    "dietary_riboflavin_sum": ("micro:riboflavin_mg", "g", (0, 0.5), 1000, "mg"),
    "dietary_pantothenic_acid_sum": ("micro:pantothenic_acid_mg", "g", (0, 1), 1000, "mg"),
    "dietary_vitamin_b6_sum": ("micro:vitamin_b6_mg", "g", (0, 0.5), 1000, "mg"),
    "dietary_vitamin_c_sum": ("micro:vitamin_c_mg", "g", (0, 10), 1000, "mg"),
    "dietary_vitamin_e_sum": ("micro:vitamin_e_mg", "g", (0, 1), 1000, "mg"),
    "dietary_vitamin_a_sum": ("micro:vitamin_a_ug", "g", (0, 0.05), 1e6, "µg"),
    "dietary_vitamin_b12_sum": ("micro:vitamin_b12_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_vitamin_d_sum": ("micro:vitamin_d_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_vitamin_k_sum": ("micro:vitamin_k_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_folate_sum": ("micro:folate_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_biotin_sum": ("micro:biotin_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_iodine_sum": ("micro:iodine_ug", "g", (0, 0.01), 1e6, "µg"),
    "dietary_selenium_sum": ("micro:selenium_ug", "g", (0, 0.01), 1e6, "µg"),
}

# Series that are not in config/defaults.json → metrics_catalog travel with their meta.
SERIES_META = {
    "wrist_temp_c": {"unit": "°C", "label": "Wrist temperature", "agg": "mean", "better": None},
    "running_power_w": {"unit": "W", "label": "Running power", "agg": "mean", "better": None},
    "walking_asymmetry_pct": {"unit": "%", "label": "Walking asymmetry", "agg": "mean", "better": "lower"},
    "walking_double_support_pct": {"unit": "%", "label": "Double support time", "agg": "mean", "better": "lower"},
    "walking_speed_mps": {"unit": "m/s", "label": "Walking speed", "agg": "mean", "better": "higher"},
    "stand_min": {"unit": "min", "label": "Stand time", "agg": "sum", "better": "higher"},
    "exercise_min": {"unit": "min", "label": "Exercise time", "agg": "sum", "better": "higher"},
    "distance_walk_run_m": {"unit": "m", "label": "Walking + running distance", "agg": "sum", "better": "higher"},
}

IGNORED_ROW_KEYS = {"date", "day", "record_count", "timezone"}

SPORT = {
    "running": "run", "walking": "walk", "hiking": "hike", "cycling": "ride", "swimming": "swim", "rowing": "row",
    "traditional_strength_training": "strength", "functional_strength_training": "strength", "strength_training": "strength",
    "high_intensity_interval_training": "hiit", "yoga": "yoga", "pilates": "mobility", "flexibility": "mobility",
    "mobility": "mobility", "cooldown": "mobility", "elliptical": "elliptical", "mixed_cardio": "other",
}

WORKOUT_FIELDS = {  # Muse field -> (workout field, plausible range)
    "distance_meters": ("distance_m", (0, 500000)),
    "hr_average_bpm": ("avg_hr", (25, 250)),
    "hr_max_bpm": ("max_hr", (25, 250)),
    "energy_burned_kcal": ("active_kcal", (0, 20000)),
    "average_speed_mps": ("avg_speed_mps", (0, 40)),
    "max_speed_mps": ("max_speed_mps", (0, 60)),
    "elevation_gain_meters": ("elevation_gain_m", (0, 10000)),
    "elevation_descended_meters": ("elevation_loss_m", (0, 10000)),
    "active_duration_sec": ("moving_s", (0, 172800)),
    "average_mets": ("avg_mets", (0, 25)),
    "step_count": ("steps", (0, 200000)),
    "flights_climbed": ("flights", (0, 2000)),
}
SEGMENT_FIELDS = {
    "distance_meters": ("distance_m", (0, 500000)), "active_duration_secs": ("moving_s", (0, 172800)),
    "hr_average_bpm": ("avg_hr", (25, 250)), "hr_max_bpm": ("max_hr", (25, 250)), "average_speed_mps": ("avg_speed_mps", (0, 40)),
    "energy_burned_kcal": ("kcal", (0, 20000)), "step_count": ("steps", (0, 200000)), "flights_climbed": ("flights", (0, 2000)),
}
SPLIT_M = 1000.0
SPLIT_TOLERANCE_M = 15.0


class MuseError(ValueError):
    pass


def num(v):
    """Muse sends counts as floats (6.0) and sometimes numbers as strings. Absent or empty stays None."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        raise MuseError(f"not a number: {v!r}")


def boolean(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise MuseError(f"not a boolean: {v!r}")


def _r(v, nd=2):
    return None if v is None else round(v, nd)


def _domain(env, name):
    d = env.get(name)
    if d is None:
        return [], None
    if isinstance(d, list):
        return d, None
    if not isinstance(d, dict):
        raise MuseError(f"{name} must be an object with coverage and records")
    recs = d.get("records") or []
    if not isinstance(recs, list):
        raise MuseError(f"{name}.records must be a list")
    return recs, d.get("coverage")


def _coverage(c):
    if not isinstance(c, dict):
        return None
    complete = c.get("complete")
    complete = boolean(complete) if not isinstance(complete, bool) else complete
    return {"complete": complete, "note": (c.get("warning") or None) and str(c["warning"])[:300]}


def _ranged(field, raw, rng, rejected, rid, domain):
    try:
        v = num(raw)
    except MuseError as e:
        rejected.append({"domain": domain, "source_id": rid, "field": field, "value": raw, "reason": str(e)})
        return None
    if v is None:
        return None
    lo, hi = rng
    if not (lo <= v <= hi):
        rejected.append({"domain": domain, "source_id": rid, "field": field, "value": v,
                         "reason": f"outside the plausible range {lo}-{hi}; not converted"})
        return None
    return v


def _sleep(rec, tz, rejected):
    rid = rec.get("id")
    if not rid:
        rejected.append({"domain": "sleep", "source_id": None, "reason": "sleep session without an id"})
        return None
    try:
        rtz = rec.get("timezone") or tz
        start, end = tu.localize(rec.get("start_datetime"), rtz), tu.localize(rec.get("end_datetime"), rtz)
    except (ValueError, TypeError) as e:
        rejected.append({"domain": "sleep", "source_id": rid, "reason": f"bad start/end: {e}"})
        return None
    if not start or not end:
        rejected.append({"domain": "sleep", "source_id": rid, "reason": "start_datetime and end_datetime are required"})
        return None
    stages = {}
    for key, stage in (("sleep_awake_duration_sec", "awake"), ("sleep_core_duration_sec", "core"), ("sleep_deep_duration_sec", "deep"),
                       ("sleep_rem_duration_sec", "rem"), ("sleep_asleep_unspecified_duration_sec", "asleep_unspecified"),
                       ("sleep_in_bed_duration_sec", "in_bed")):
        v = _ranged(key, rec.get(key), (0, 86400), rejected, rid, "sleep")
        if v is not None:
            stages[stage] = round(v / 60.0, 1)
    night = {"source_id": rid, "date": tu.parse_ts(end).date().isoformat(), "start": start, "end": end, "source": "healthkit"}
    if stages:
        night["stage_minutes"] = stages
    eff = _ranged("sleep_efficiency", rec.get("sleep_efficiency"), (1, 100), rejected, rid, "sleep")
    if eff is not None:
        night["efficiency_pct"] = round(eff, 1)
    aw = _ranged("number_of_awakenings", rec.get("number_of_awakenings"), (0, 200), rejected, rid, "sleep")
    if aw is not None:
        night["awakenings"] = int(round(aw))
    return night


def _epoch(v, tzname):
    return datetime.fromtimestamp(float(v), timezone.utc).astimezone(tu.tzinfo(tzname)).isoformat()


def _workout(rec, tz, rejected):
    rid = rec.get("id")
    if not rid:
        rejected.append({"domain": "workouts", "source_id": None, "reason": "workout without an id"})
        return None
    rtz = rec.get("timezone") or tz
    try:
        start, end = tu.localize(rec.get("start_datetime"), rtz), tu.localize(rec.get("end_datetime"), rtz)
        indoor = boolean(rec.get("is_indoor"))
    except (ValueError, TypeError) as e:
        rejected.append({"domain": "workouts", "source_id": rid, "reason": f"bad field: {e}"})
        return None
    if not start or not end:
        rejected.append({"domain": "workouts", "source_id": rid, "reason": "start_datetime and end_datetime are required"})
        return None
    wt = str(rec.get("workout_type") or "other").strip().lower()
    sport = SPORT.get(wt, "other")
    if sport == "run" and indoor:
        sport = "treadmill_run"
    t0, t1 = tu.parse_ts(start), tu.parse_ts(end)
    w = {"source_id": rid, "sport": sport, "start": start, "end": end, "duration_s": round((t1 - t0).total_seconds()),
         "source": "healthkit", "indoor": indoor}
    if sport == "other" and wt not in ("other", ""):
        w["name"] = wt.replace("_", " ").capitalize()
    for k, (field, rng) in WORKOUT_FIELDS.items():
        v = _ranged(k, rec.get(k), rng, rejected, rid, "workouts")
        if v is not None:
            w[field] = round(v) if field in ("steps", "flights") else _r(v)
    temp = _ranged("weather_temperature_celsius", rec.get("weather_temperature_celsius"), (-50, 60), rejected, rid, "workouts")
    hum = _ranged("weather_humidity_percent", rec.get("weather_humidity_percent"), (0, 100), rejected, rid, "workouts")
    if temp is not None or hum is not None:
        w["weather"] = {"temp_c": _r(temp, 1), "humidity_pct": _r(hum, 0), "source": "healthkit"}
    splits, laps = [], []
    segs = rec.get("segments") or rec.get("workout_segments") or []
    for s in sorted(segs, key=lambda x: num(x.get("start_epoch_sec")) or 0):
        try:
            s0, s1 = num(s.get("start_epoch_sec")), num(s.get("end_epoch_sec"))
        except MuseError as e:
            rejected.append({"domain": "workouts", "source_id": rid, "field": "segments", "reason": str(e)})
            continue
        if s0 is None or s1 is None or s1 <= s0:
            rejected.append({"domain": "workouts", "source_id": rid, "field": "segments", "reason": "segment needs increasing start_epoch_sec/end_epoch_sec"})
            continue
        row = {}
        for k, (field, rng) in SEGMENT_FIELDS.items():
            v = _ranged(f"segments.{k}", s.get(k), rng, rejected, rid, "workouts")
            if v is not None:
                row[field] = round(v) if field in ("steps", "flights") else _r(v)
        dist = row.get("distance_m")
        is_split = str(s.get("segment_type") or "").lower() == "segment" and dist is not None and abs(dist - SPLIT_M) <= SPLIT_TOLERANCE_M
        if is_split:
            splits.append(dict(index=len(splits), start=_epoch(s0, rtz), end=_epoch(s1, rtz), duration_s=round(s1 - s0), **row))
        else:
            laps.append(dict(start_s=round(s0 - t0.timestamp(), 1), end_s=round(s1 - t0.timestamp(), 1), label=str(s.get("segment_type") or "lap"), **row))
    if splits:
        w["splits"] = splits
    if laps:
        w["laps"] = laps
    return w


def _daily_row(rec, tz, gen_date, rejected, out):
    d = rec.get("date") if rec.get("date") is not None else rec.get("day")
    try:
        day = tu.parse_date(d).isoformat() if d else None
        if day and len(str(d)) != 10:
            raise ValueError(d)
    except (ValueError, TypeError):
        day = None
    if not day:
        rejected.append({"domain": "daily_metrics", "source_id": None, "keys": sorted(rec)[:12],
                         "reason": "daily metric row needs 'date' (YYYY-MM-DD); found " + (repr(d) if d else "no date field")})
        return
    nut, micros = {}, {}
    for field, raw in rec.items():
        if field in IGNORED_ROW_KEYS:
            continue
        spec = UNITS.get(field)
        if spec is None:
            out["ignored_fields"].add(field)
            continue
        target, _, rng, factor, _ = spec
        sid = f"healthkit_daily_{target.split(':', 1)[1]}_{day}"
        v = _ranged(field, raw, rng, rejected, sid, "daily_metrics")
        if v is None:
            continue
        v = v * factor
        kind, key = target.split(":", 1)
        if kind == "metric":
            out["metrics"].setdefault(key, []).append({"date": day, "v": round(v, 3), "source_id": sid})
        elif kind == "body":
            out["body"].append({"source_id": sid, "t": tu.localize(f"{day} 00:00:00", tz), "type": key, "v": round(v, 2)})
        elif kind == "nutrition":
            nut[key] = round(v, 1)
        else:
            micros[key] = round(v, 3)
    if nut or micros:
        row = {"source_id": f"healthkit_daily_nutrition_{day}", "date": day, **nut}
        if micros:
            row["micros"] = micros
        out["daily_totals"].append(row)


def to_batch(env):
    """Returns (batch, rejected, info). Raises MuseError for an unusable envelope."""
    if not isinstance(env, dict) or env.get("format") != FORMAT:
        raise MuseError(f"format must be {FORMAT!r}")
    tz = env.get("timezone")
    if not tz:
        raise MuseError("timezone is required (an IANA name such as Africa/Kigali)")
    try:
        tu.tzinfo(tz)
    except Exception:
        raise MuseError(f"unknown timezone {tz!r}")
    try:
        gen = tu.localize(env.get("generated_at"), tz)
    except (ValueError, TypeError) as e:
        raise MuseError(f"generated_at: {e}")
    if not gen:
        raise MuseError("generated_at is required")
    gen_date = tu.parse_ts(gen).astimezone(tu.tzinfo(tz)).date().isoformat()
    rejected = []
    out = {"metrics": {}, "body": [], "daily_totals": [], "ignored_fields": set()}
    sleep_recs, sleep_cov = _domain(env, "sleep")
    work_recs, work_cov = _domain(env, "workouts")
    daily_recs, daily_cov = _domain(env, "daily_metrics")
    nights = [n for n in (_sleep(r, tz, rejected) for r in sleep_recs if isinstance(r, dict)) if n]
    workouts = [w for w in (_workout(r, tz, rejected) for r in work_recs if isinstance(r, dict)) if w]
    for r in daily_recs:
        if isinstance(r, dict):
            _daily_row(r, tz, gen_date, rejected, out)
    coverage = {}
    for dom, cov, recs in (("sleep", sleep_cov, nights), ("workouts", work_cov, workouts), ("metrics", daily_cov, None)):
        c = _coverage(cov)
        if c is not None:
            coverage[dom] = c
    # an incomplete query leaves its latest day partial; the next re-send replaces those values
    def mark(records, key):
        if records:
            last = max(key(r) for r in records)
            for r in records:
                if key(r) == last:
                    r["partial"] = True
    if coverage.get("sleep", {}).get("complete") is False:
        mark(nights, lambda n: n["date"])
    if coverage.get("workouts", {}).get("complete") is False:
        mark(workouts, lambda w: tu.parse_ts(w["start"]).astimezone(tu.tzinfo(tz)).date().isoformat())
    if coverage.get("metrics", {}).get("complete") is False:
        days = [p["date"] for pts in out["metrics"].values() for p in pts] + [r["date"] for r in out["daily_totals"]]
        if days:
            last = max(days)
            for pts in out["metrics"].values():
                for p in pts:
                    if p["date"] == last:
                        p["partial"] = True
            for r in out["daily_totals"]:
                if r["date"] == last:
                    r["partial"] = True
            for m in out["body"]:
                if m["t"][:10] == last:
                    m["partial"] = True
    samples = {}
    if out["metrics"]:
        samples["metrics"] = out["metrics"]
    if nights:
        samples["sleep"] = nights
    if workouts:
        samples["workouts"] = workouts
    if out["body"]:
        samples["body"] = out["body"]
    if out["daily_totals"]:
        samples["nutrition"] = {"daily_totals": out["daily_totals"]}
    used_meta = {k: v for k, v in SERIES_META.items() if k in out["metrics"]}
    batch = {"batch_version": 2, "date": gen_date, "generated_at": gen, "timezone": tz, "source": "healthkit", "samples": samples}
    if used_meta:
        batch["series_meta"] = used_meta
    if coverage:
        batch["coverage"] = coverage
    info = {"format": FORMAT, "ignored_fields": sorted(out["ignored_fields"]),
            "records_in": {"sleep": len(sleep_recs), "workouts": len(work_recs), "daily_metrics": len(daily_recs)}}
    return batch, rejected, info
