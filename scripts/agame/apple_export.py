"""One-time backfill from Apple Health's export.zip (export.xml + workout-routes/*.gpx). Standard library only.

- export.xml is streamed twice with iterparse: pass 1 reads daily values, sleep and workouts; pass 2 keeps only the
  heart-rate samples that fall inside a workout (or the last few days, for the stress estimate). Memory stays flat.
- Daily values use exactly the ids Muse uses (healthkit_daily_<series>_<date>), so the two never duplicate.
  Apple's export carries no record UUIDs, so sleep nights and workouts get a stable id derived from their content
  (healthkit_<uuid5>); the importer's same-thing matching keeps them from duplicating Muse's records, and the detailed
  export copy replaces Muse's summary of the same night or workout.
- Steps, energy and distance are written by several devices at once. Per day the largest single-device total is kept,
  so iPhone and Watch are never added together.
- Units come from each record's own unit attribute. A unit this file does not know is skipped and counted, never guessed.
"""

import bisect
import io
import math
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agame import muse
from agame import timeutil as tu

NS = uuid.UUID("6b7f1a3e-6a0c-4e43-9b3c-41a6e0ad5a11")
HK = "HKQuantityTypeIdentifier"
INTRADAY_HR_DAYS = 14
SAMPLE_EVERY_S = 2

# unit conversions to the stored unit; anything missing here is skipped and reported
UNIT = {
    "ms": ("ms", 1), "count/min": ("bpm", 1), "%": ("frac", 1), "kg": ("kg", 1), "lb": ("kg", 0.45359237), "g": ("g", 1),
    "mg": ("g", 0.001), "mcg": ("g", 1e-6), "kcal": ("kcal", 1), "Cal": ("kcal", 1), "kJ": ("kcal", 0.239006), "count": ("count", 1),
    "m": ("m", 1), "cm": ("m", 0.01), "km": ("m", 1000), "mi": ("m", 1609.344), "ft": ("m", 0.3048), "mL": ("mL", 1), "L": ("mL", 1000),
    "fl_oz_us": ("mL", 29.5735), "degC": ("C", 1), "mmHg": ("mmHg", 1), "mg/dL": ("mg/dL", 1), "W": ("W", 1), "min": ("min", 1),
    "m/s": ("m/s", 1), "km/hr": ("m/s", 1 / 3.6), "mi/hr": ("m/s", 0.44704), "ml/(kg*min)": ("ml/kg/min", 1),
    "mL/min·kg": ("ml/kg/min", 1), "mL/(kg·min)": ("ml/kg/min", 1),
}
# HK type -> (muse field it stands in for, expected stored unit, aggregation per day)
DAILY = {
    "HeartRateVariabilitySDNN": ("heart_rate_variability_ms", "ms", "mean"),
    "RestingHeartRate": ("resting_hr_average_bpm", "bpm", "mean"),
    "RespiratoryRate": ("respiratory_rate_average", "bpm", "mean"),
    "OxygenSaturation": ("oxygen_saturation_average", "frac", "mean"),
    "AppleSleepingWristTemperature": ("apple_sleeping_wrist_temperature_average", "C", "mean"),
    "VO2Max": ("vo2_max", "ml/kg/min", "mean"),
    "HeartRateRecoveryOneMinute": ("heart_rate_recovery_one_minute_average", "bpm", "mean"),
    "WalkingHeartRateAverage": ("walking_heart_rate_average_average", "bpm", "mean"),
    "StepCount": ("step_count", "count", "device_sum"),
    "ActiveEnergyBurned": ("active_energy_burned_kcal", "kcal", "device_sum"),
    "BasalEnergyBurned": ("basal_energy_burned_kcal", "kcal", "device_sum"),
    "DistanceWalkingRunning": ("distance_walking_running_meters", "m", "device_sum"),
    "AppleStandTime": ("apple_stand_time_sum", "min", "device_sum"),
    "AppleExerciseTime": ("apple_exercise_time_sum", "min", "device_sum"),
    "RunningGroundContactTime": ("running_ground_contact_time_average", "ms", "mean"),
    "RunningStrideLength": ("running_stride_length_average", "m", "mean"),
    "RunningVerticalOscillation": ("running_vertical_oscillation_average", "m", "mean"),
    "RunningPower": ("running_power_average", "W", "mean"),
    "WalkingSpeed": ("walking_speed_average", "m/s", "mean"),
    "WalkingAsymmetryPercentage": ("walking_asymmetry_percentage_average", "frac", "mean"),
    "WalkingDoubleSupportPercentage": ("walking_double_support_percentage_average", "frac", "mean"),
    "BloodPressureSystolic": ("blood_pressure_systolic_average", "mmHg", "mean"),
    "BloodPressureDiastolic": ("blood_pressure_diastolic_average", "mmHg", "mean"),
    "BloodGlucose": ("blood_glucose_average", "mg/dL", "mean"),
    "BodyMass": ("body_mass_average", "kg", "mean"),
    "BodyFatPercentage": ("body_fat_percentage", "frac", "mean"),
    "LeanBodyMass": ("lean_body_mass_average", "kg", "mean"),
    "WaistCircumference": ("waist_circumference_average", "m", "mean"),
    "BodyMassIndex": ("bmi", "count", "mean"),
}
for _n, _f in (("Energy", "energy"), ("Protein", "protein"), ("Carbohydrates", "carbs"), ("FatTotal", "fat"), ("Fiber", "fiber"),
               ("Sugar", "sugar"), ("Sodium", "sodium"), ("Water", "water"), ("FatSaturated", "fat_saturated"),
               ("FatMonounsaturated", "fat_monounsaturated"), ("FatPolyunsaturated", "fat_polyunsaturated"), ("Cholesterol", "cholesterol"),
               ("Potassium", "potassium"), ("Calcium", "calcium"), ("Iron", "iron"), ("Magnesium", "magnesium"), ("Zinc", "zinc"),
               ("VitaminC", "vitamin_c"), ("VitaminD", "vitamin_d"), ("VitaminA", "vitamin_a"), ("VitaminB12", "vitamin_b12")):
    DAILY["Dietary" + _n] = (f"dietary_{_f}_sum", "kcal" if _n == "Energy" else ("mL" if _n == "Water" else "g"), "device_sum")

SLEEP_STAGE = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed", "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core", "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem", "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",
}
SLEEP_GAP = timedelta(hours=2)
WORKOUT_SPORT = {
    "Running": "running", "Walking": "walking", "Hiking": "hiking", "Cycling": "cycling", "Swimming": "swimming", "Rowing": "rowing",
    "TraditionalStrengthTraining": "traditional_strength_training", "FunctionalStrengthTraining": "functional_strength_training",
    "HighIntensityIntervalTraining": "high_intensity_interval_training", "Yoga": "yoga", "Pilates": "pilates", "Flexibility": "flexibility",
    "Cooldown": "cooldown", "Elliptical": "elliptical", "MixedCardio": "mixed_cardio",
}


class ExportError(ValueError):
    pass


def _ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def _conv(value, unit):
    if unit == "degF":  # the only unit here with an offset
        try:
            return (float(value) - 32) * 5 / 9, "C"
        except (TypeError, ValueError):
            return None, None
    u = UNIT.get(unit)
    if u is None:
        return None, None
    try:
        return float(value) * u[1], u[0]
    except (TypeError, ValueError):
        return None, None


class Source:
    """export.zip, an unzipped export folder, or export.xml itself."""

    def __init__(self, path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path) if zipfile.is_zipfile(self.path) else None
        if self.zip:
            names = [n for n in self.zip.namelist() if n.endswith("export.xml") and "export_cda" not in n]
            if not names:
                raise ExportError("export.xml not found in the zip")
            self.xml_name = names[0]
            self.root = self.xml_name.rsplit("export.xml", 1)[0]
        else:
            self.xml_path = self.path if self.path.suffix == ".xml" else self.path / "export.xml"
            if not self.xml_path.is_file():
                raise ExportError(f"no export.xml at {self.xml_path}")

    def xml(self):
        return self.zip.open(self.xml_name) if self.zip else open(self.xml_path, "rb")

    def file(self, ref):
        ref = ref.lstrip("/")
        if self.zip:
            try:
                return self.zip.open(self.root + ref).read()
            except KeyError:
                return None
        p = self.xml_path.parent / ref
        return p.read_bytes() if p.is_file() else None

    def check_safe(self):
        with self.xml() as fh:
            head = fh.read(1 << 20).decode("utf-8", "replace")
        if re.search(r"<!ENTITY", head, re.I):
            raise ExportError("export.xml declares XML entities; refusing to parse it")


def _iter(src, tags):
    with src.xml() as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag in tags:
                yield el
                el.clear()
            elif el.tag in ("ActivitySummary", "ClinicalRecord", "Correlation"):
                el.clear()


def _gpx_points(raw):
    if not raw or re.search(rb"<!DOCTYPE|<!ENTITY", raw[:4096], re.I):
        return []
    out = []
    for _, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag.endswith("trkpt"):
            t = ele = None
            for c in el:
                if c.tag.endswith("time"):
                    t = c.text
                elif c.tag.endswith("ele"):
                    ele = c.text
            if t:
                try:
                    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    out.append((dt, float(el.get("lat")), float(el.get("lon")), float(ele) if ele else None))
                except (TypeError, ValueError):
                    pass
            el.clear()
    return out


def _haversine(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _workout(el, tzname, stats):
    kind = (el.get("workoutActivityType") or "").replace("HKWorkoutActivityType", "")
    start, end = _ts(el.get("startDate")), _ts(el.get("endDate"))
    rec = {"id": "healthkit_" + str(uuid.uuid5(NS, f"workout|{kind}|{start.isoformat()}|{end.isoformat()}")).upper(),
           "start_datetime": start.isoformat(), "end_datetime": end.isoformat(), "timezone": tzname,
           "workout_type": WORKOUT_SPORT.get(kind, kind.lower() or "other")}
    meta, route = {}, None
    for c in el:
        if c.tag == "MetadataEntry":
            meta[c.get("key")] = c.get("value")
        elif c.tag == "WorkoutStatistics":
            t = (c.get("type") or "").replace(HK, "")
            if t == "HeartRate":
                rec["hr_average_bpm"], rec["hr_max_bpm"] = c.get("average"), c.get("maximum")
            elif t in ("DistanceWalkingRunning", "DistanceCycling", "DistanceSwimming"):
                v, u = _conv(c.get("sum"), c.get("unit"))
                if u == "m":
                    rec["distance_meters"] = v
            elif t == "ActiveEnergyBurned":
                v, u = _conv(c.get("sum"), c.get("unit"))
                if u == "kcal":
                    rec["energy_burned_kcal"] = v
            elif t == "StepCount":
                rec["step_count"] = c.get("sum")
        elif c.tag == "WorkoutRoute":
            for f in c:
                if f.tag == "FileReference":
                    route = f.get("path")
    if "distance_meters" not in rec and el.get("totalDistance"):
        v, u = _conv(el.get("totalDistance"), el.get("totalDistanceUnit"))
        if u == "m":
            rec["distance_meters"] = v
    if "energy_burned_kcal" not in rec and el.get("totalEnergyBurned"):
        v, u = _conv(el.get("totalEnergyBurned"), el.get("totalEnergyBurnedUnit"))
        if u == "kcal":
            rec["energy_burned_kcal"] = v
    if meta.get("HKIndoorWorkout") is not None:
        rec["is_indoor"] = "true" if meta["HKIndoorWorkout"] in ("1", "true") else "false"
    m = re.match(r"([\d.]+) cm", meta.get("HKElevationAscended") or "")
    if m:
        rec["elevation_gain_meters"] = float(m.group(1)) / 100
    m = re.match(r"([\d.]+) deg([CF])", meta.get("HKWeatherTemperature") or "")
    if m:
        rec["weather_temperature_celsius"] = float(m.group(1)) if m.group(2) == "C" else (float(m.group(1)) - 32) * 5 / 9
    m = re.match(r"([\d.]+) %", meta.get("HKWeatherHumidity") or "")
    if m:
        h = float(m.group(1))
        rec["weather_humidity_percent"] = h / 100 if h > 100 else h  # Apple writes 65 % as "6500 %"
    stats["workouts"] += 1
    return rec, route, start, end


def _nights(segments, tzname):
    """Group stage segments into nights; per night keep one device (the one with real stages, most data)."""
    nights = []
    for seg in sorted(segments, key=lambda s: s[1]):
        if nights and seg[1] - nights[-1]["end"] <= SLEEP_GAP:
            nights[-1]["segs"].append(seg)
            nights[-1]["end"] = max(nights[-1]["end"], seg[2])
        else:
            nights.append({"segs": [seg], "end": seg[2]})
    out = []
    for n in nights:
        by_src = defaultdict(list)
        for s in n["segs"]:
            by_src[s[3]].append(s)
        best = max(by_src.values(), key=lambda ss: (any(x[0] in ("core", "deep", "rem") for x in ss), sum((x[2] - x[1]).total_seconds() for x in ss)))
        start, end = min(x[1] for x in best), max(x[2] for x in best)
        sid = "healthkit_" + str(uuid.uuid5(NS, f"sleep|{start.isoformat()}|{end.isoformat()}")).upper()
        local_end = end.astimezone(tu.tzinfo(tzname))
        out.append({"source_id": sid, "date": local_end.date().isoformat(), "start": start.isoformat(), "end": end.isoformat(), "source": "healthkit",
                    "segments": [{"stage": st, "start": a.isoformat(), "end": b.isoformat()} for st, a, b, _ in sorted(best, key=lambda x: x[1]) if b > a]})
    return out


def read_export(path, tzname, now=None, progress=None):
    """Returns (muse_like_envelope_parts, workouts_with_samples, nights, stats). Raises ExportError."""
    tz = tu.tzinfo(tzname)
    src = Source(path)
    src.check_safe()
    stats = defaultdict(int)
    daily = defaultdict(lambda: defaultdict(list))        # (date) -> field -> [values]
    device = defaultdict(lambda: defaultdict(float))       # (date, field, source) -> sum
    sleep_segs, workouts, export_date = [], [], None
    for el in _iter(src, {"Record", "Workout", "ExportDate"}):
        if el.tag == "ExportDate":
            export_date = el.get("value")
            continue
        if el.tag == "Workout":
            workouts.append(_workout(el, tzname, stats))
            continue
        typ = el.get("type") or ""
        if typ == "HKCategoryTypeIdentifierSleepAnalysis":
            st = SLEEP_STAGE.get(el.get("value"))
            if st:
                sleep_segs.append((st, _ts(el.get("startDate")), _ts(el.get("endDate")), el.get("sourceName") or ""))
            continue
        short = typ.replace(HK, "")
        spec = DAILY.get(short)
        if not spec:
            continue
        field, want, agg = spec
        v, unit = _conv(el.get("value"), el.get("unit"))
        if v is None or unit != want:
            stats[f"skipped_unit:{short}:{el.get('unit')}"] += 1
            continue
        day = _ts(el.get("startDate")).astimezone(tz).date().isoformat()
        if agg == "mean":
            daily[day][field].append(v)
        else:
            device[(day, field)][el.get("sourceName") or ""] += v
        stats["records"] += 1
        if progress and stats["records"] % 200000 == 0:
            progress(f"read {stats['records']} records")
    rows = defaultdict(dict)
    for day, fields in daily.items():
        for f, vs in fields.items():
            rows[day][f] = sum(vs) / len(vs)
    for (day, f), per_src in device.items():
        rows[day][f] = max(per_src.values())
    daily_records = [dict(date=d, **r) for d, r in sorted(rows.items())]
    # pass 2: heart-rate samples inside workouts and in the last days
    wins = sorted((s, e, i) for i, (_, _, s, e) in enumerate(workouts))
    recent_from = (now or datetime.now(timezone.utc)) - timedelta(days=INTRADAY_HR_DAYS)
    hr_by_workout = defaultdict(list)
    intraday = []
    if wins:
        starts = [w[0] for w in wins]
        for el in _iter(src, {"Record"}):
            if el.get("type") != HK + "HeartRate":
                continue
            t = _ts(el.get("startDate"))
            try:
                v = float(el.get("value"))
            except (TypeError, ValueError):
                continue
            k = bisect.bisect_right(starts, t) - 1
            if k >= 0 and wins[k][0] <= t <= wins[k][1]:
                hr_by_workout[wins[k][2]].append((t, v))
            if t >= recent_from:
                intraday.append((t, v))
    for i, (rec, route, start, end) in enumerate(workouts):
        rec["_samples"] = _samples(src, route, start, hr_by_workout.get(i, []), stats)
    nights = _nights(sleep_segs, tzname)
    stats["nights"] = len(nights)
    return {"export_date": export_date, "daily": daily_records, "workouts": workouts, "nights": nights, "intraday_hr": intraday, "stats": dict(stats)}


def _samples(src, route, start, hr, stats):
    pts = _gpx_points(src.file(route)) if route else []
    if pts:
        stats["routes"] += 1
    rows = {}
    last_gps_t = None
    dist = 0.0
    prev = None
    for dt, lat, lon, ele in pts:
        sec = round((dt - start).total_seconds())
        if sec < 0:
            continue
        if prev:
            dist += _haversine(prev, (lat, lon))
        prev = (lat, lon)
        if last_gps_t is not None and sec - last_gps_t < SAMPLE_EVERY_S:
            continue
        last_gps_t = sec
        rows[sec] = {"lat": round(lat, 6), "lon": round(lon, 6), "elev_m": round(ele, 1) if ele is not None else None, "dist_m": round(dist, 1)}
    for dt, v in hr:
        sec = round((dt - start).total_seconds())
        if sec >= 0:
            rows.setdefault(sec, {})["hr"] = round(v)
    if len(rows) < 2:
        return None
    keys = sorted(rows)
    out = {"t": keys}
    for f in ("hr", "dist_m", "elev_m", "lat", "lon"):
        col = [rows[k].get(f) for k in keys]
        if any(v is not None for v in col):
            out[f] = col
    return out


def to_batches(parsed, tzname, generated_at):
    """Turn a parsed export into AGame batches: one muse.v1-shaped batch for summaries plus one with detail."""
    env = {"format": "muse.v1", "generated_at": generated_at, "timezone": tzname,
           "daily_metrics": {"records": parsed["daily"]},
           "workouts": {"records": [{k: v for k, v in w[0].items() if k != "_samples"} for w in parsed["workouts"]]}}
    batch, rejected, info = muse.to_batch(env)
    for w in batch["samples"].get("workouts", []):
        src = next((x[0] for x in parsed["workouts"] if x[0]["id"] == w["source_id"]), None)
        if src and src.get("_samples"):
            w["samples"] = src["_samples"]
    if parsed["nights"]:
        batch["samples"]["sleep"] = parsed["nights"]
    if parsed["intraday_hr"]:
        batch["samples"].setdefault("metrics", {})["heart_rate_bpm"] = [
            {"t": t.isoformat(), "v": v, "source_id": "healthkit_" + str(uuid.uuid5(NS, f"hr|{t.isoformat()}|{v}")).upper()} for t, v in parsed["intraday_hr"]]
    batch["source"] = "healthkit_export"
    return batch, rejected, info


def run(path, data_dir, tzname=None, dry_run=False, progress=None):
    """Parse an export and import it (lenient: odd records are listed, never fatal). Returns (summary, exit_code)."""
    from agame.datastore import load_all
    from agame.importer import apply_batch
    data, _, _ = load_all(data_dir)
    tzname = tzname or ((data.get("profile") or {}).get("locale") or {}).get("timezone") or tu.DEFAULT_TZ
    parsed = read_export(path, tzname, progress=progress)
    gen = _ts(parsed["export_date"]).isoformat() if parsed.get("export_date") else datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    batch, rejected, info = to_batches(parsed, tzname, gen)
    if progress:
        progress("importing")
    summary, code = apply_batch(data_dir, batch, dry_run=dry_run, lenient=True)
    summary["rejected"] = rejected + [r for r in summary.get("rejected", []) if r not in rejected]
    summary["export"] = {"export_date": parsed.get("export_date"), "daily_rows": len(parsed["daily"]), **parsed["stats"]}
    if summary["rejected"] and code == 0:
        code = 2
    return summary, code
