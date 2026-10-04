"""Schema + semantic validation for the data directory.

Errors block the build (impossible or inconsistent data). Warnings do not.
"""

import json
from datetime import timedelta

from agame import timeutil as tu
from agame.datastore import load_all
from agame.jsonschema_lite import Validator
from agame.paths import DATA_FILES, SCHEMA_DIR, domain_of, load_config, load_exercise_library

RANGES = {
    "resting_hr_bpm": (20, 150),
    "hrv_sdnn_ms": (1, 400),
    "vo2max_ml_kg_min": (10, 95),
    "heart_rate_bpm": (20, 250),
    "walking_hr_bpm": (30, 220),
    "respiratory_rate_brpm": (4, 60),
    "steps": (0, 150000),
    "spo2_pct": (50, 100),
    "active_energy_kcal": (0, 15000),
    "resting_energy_kcal": (0, 6000),
    "bp_systolic_mmhg": (50, 260),
    "bp_diastolic_mmhg": (30, 180),
    "glucose_mg_dl": (20, 600),
    "hr_recovery_bpm": (0, 120),
}
BODY_RANGES = {"weight_kg": (20, 400), "body_fat_pct": (2, 70), "lean_mass_kg": (10, 200), "waist_cm": (30, 250), "bmi": (8, 80)}


def _schemas():
    out = {}
    for f in DATA_FILES:
        d = domain_of(f)
        with open(SCHEMA_DIR / f"{d}.schema.json", encoding="utf-8") as fh:
            out[d] = json.load(fh)
    return out


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, file, pointer, msg):
        self.errors.append({"file": file, "pointer": pointer or "/", "message": msg, "severity": "error"})

    def warn(self, file, pointer, msg):
        self.warnings.append({"file": file, "pointer": pointer or "/", "message": msg, "severity": "warning"})

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _fname(domain):
    return "routes.geojson" if domain == "routes" else f"{domain}.json"


def _ts(rep, file, pointer, value, horizon):
    try:
        dt = tu.parse_ts(value)
    except (ValueError, TypeError) as exc:
        rep.err(file, pointer, f"bad timestamp: {exc}")
        return None
    if horizon is not None and dt > horizon:
        rep.err(file, pointer, f"timestamp {value} is in the future (after {horizon.isoformat()})")
    return dt


def _dupes(rep, file, items, key, pointer_base):
    seen = {}
    for i, it in enumerate(items):
        k = it.get(key)
        if k is None:
            continue
        if k in seen:
            rep.err(file, f"{pointer_base}/{i}/{key}", f"duplicate {key} {k!r} (also at index {seen[k]})")
        else:
            seen[k] = i


def semantic_checks(data, rep, build_date=None):
    cfg = load_config(data.get("profile"))
    tzname = (data.get("profile", {}).get("locale") or {}).get("timezone") or tu.DEFAULT_TZ
    try:
        tz = tu.tzinfo(tzname)
    except Exception:
        rep.err("profile.json", "/locale/timezone", f"unknown timezone {tzname!r}")
        tz = tu.tzinfo(tu.DEFAULT_TZ)
    horizon = None
    if build_date is not None:
        horizon = tu.end_of_day(build_date, tz) + timedelta(hours=14)

    # profile
    prof = data.get("profile", {})
    phys = prof.get("physiology") or {}
    hrmax = (phys.get("hr_max") or {}).get("value")
    if hrmax is not None and not (120 <= hrmax <= 230):
        rep.err("profile.json", "/physiology/hr_max/value", f"implausible HR max {hrmax}")
    for k in ("hr_max", "lthr", "threshold_pace_s_per_km", "ftp_w"):
        m = phys.get(k)
        if m and m.get("kind") in (None, "observed", "configured") and not m.get("method"):
            rep.warn("profile.json", f"/physiology/{k}", "no method recorded; record how this value was obtained")
    lthr = (phys.get("lthr") or {}).get("value")
    if hrmax and lthr and lthr >= hrmax:
        rep.err("profile.json", "/physiology/lthr/value", "LTHR must be below HR max")

    # metrics
    met = data.get("metrics", {})
    catalog = cfg["metrics_catalog"]
    meta = met.get("series_meta") or {}
    for sid, pts in (met.get("series") or {}).items():
        file = "metrics.json"
        if sid not in catalog and sid not in meta:
            rep.err(file, f"/series/{sid}", f"unknown series '{sid}' needs series_meta with a unit")
        _dupes(rep, file, pts, "source_id", f"/series/{sid}")
        lo_hi = RANGES.get(sid)
        for i, p in enumerate(pts):
            if "t" in p:
                _ts(rep, file, f"/series/{sid}/{i}/t", p["t"], horizon)
            if lo_hi and not (lo_hi[0] <= p["v"] <= lo_hi[1]):
                rep.err(file, f"/series/{sid}/{i}/v", f"impossible {sid} value {p['v']}")

    # sleep
    for i, n in enumerate((data.get("sleep") or {}).get("nights", [])):
        file, base = "sleep.json", f"/nights/{i}"
        s = _ts(rep, file, f"{base}/start", n["start"], horizon)
        e = _ts(rep, file, f"{base}/end", n["end"], horizon)
        if s and e:
            if e <= s:
                rep.err(file, base, "sleep end must be after start")
            elif (e - s) > timedelta(hours=24):
                rep.err(file, base, "sleep session longer than 24 h")
        for j, seg in enumerate(n.get("segments", [])):
            ss = _ts(rep, file, f"{base}/segments/{j}/start", seg["start"], horizon)
            se = _ts(rep, file, f"{base}/segments/{j}/end", seg["end"], horizon)
            if ss and se and se <= ss:
                rep.err(file, f"{base}/segments/{j}", "segment end must be after start")
            if s and e and ss and se and (ss < s - timedelta(minutes=10) or se > e + timedelta(minutes=10)):
                rep.err(file, f"{base}/segments/{j}", "segment outside the night's start/end")
    _dupes(rep, "sleep.json", (data.get("sleep") or {}).get("nights", []), "source_id", "/nights")

    # routes
    route_ids = set()
    for i, f in enumerate((data.get("routes") or {}).get("features", [])):
        rid = f["properties"]["id"]
        if rid in route_ids:
            rep.err("routes.geojson", f"/features/{i}/properties/id", f"duplicate route id {rid!r}")
        route_ids.add(rid)
        for j, c in enumerate(f["geometry"]["coordinates"]):
            if not (-180 <= c[0] <= 180 and -90 <= c[1] <= 90):
                rep.err("routes.geojson", f"/features/{i}/geometry/coordinates/{j}", "coordinate out of range (expects [lon, lat, ele])")
                break

    # workouts
    workouts = (data.get("workouts") or {}).get("workouts", [])
    _dupes(rep, "workouts.json", workouts, "source_id", "/workouts")
    workout_ids = {w["source_id"] for w in workouts}
    for i, w in enumerate(workouts):
        file, base = "workouts.json", f"/workouts/{i}"
        s = _ts(rep, file, f"{base}/start", w["start"], horizon)
        e = _ts(rep, file, f"{base}/end", w["end"], horizon)
        if s and e:
            if e <= s:
                rep.err(file, base, "workout end must be after start")
            elif e - s > timedelta(hours=48):
                rep.err(file, base, "workout longer than 48 h")
        for k in ("avg_hr", "max_hr"):
            v = w.get(k)
            if v is not None and not (25 <= v <= 250):
                rep.err(file, f"{base}/{k}", f"impossible heart rate {v}")
        if w.get("avg_hr") and w.get("max_hr") and w["avg_hr"] > w["max_hr"]:
            rep.err(file, base, "avg_hr above max_hr")
        if w.get("distance_m") and w.get("duration_s") and w["duration_s"] > 0:
            speed = w["distance_m"] / w["duration_s"]
            limit = {"run": 7.0, "trail_run": 7.0, "track_run": 11.0, "treadmill_run": 7.5, "walk": 3.5, "hike": 3.5,
                     "swim": 3.0, "open_water_swim": 3.0, "row": 7.0}.get(w["sport"], 30.0)
            if speed > limit:
                rep.err(file, base, f"average speed {speed:.1f} m/s impossible for {w['sport']}")
        smp = w.get("samples")
        if smp:
            n = len(smp["t"])
            for k, arr in smp.items():
                if len(arr) != n:
                    rep.err(file, f"{base}/samples/{k}", f"length {len(arr)} != t length {n}")
            for j, hr in enumerate(smp.get("hr") or []):
                if hr is not None and not (25 <= hr <= 250):
                    rep.err(file, f"{base}/samples/hr/{j}", f"impossible heart rate {hr}")
                    break
            prev = None
            for j, t in enumerate(smp["t"]):
                if t is None or (prev is not None and t < prev):
                    rep.err(file, f"{base}/samples/t/{j}", "sample times must be non-null and increasing")
                    break
                prev = t
            prevd = None
            for j, d in enumerate(smp.get("dist_m") or []):
                if d is None:
                    continue
                if prevd is not None and d < prevd - 1.0:
                    rep.err(file, f"{base}/samples/dist_m/{j}", "cumulative distance decreases")
                    break
                prevd = d
        if w.get("route_id") and w["route_id"] not in route_ids:
            rep.err(file, f"{base}/route_id", f"route {w['route_id']!r} not found in routes.geojson")

    # body
    body = (data.get("body") or {}).get("measurements", [])
    _dupes(rep, "body.json", body, "source_id", "/measurements")
    for i, m in enumerate(body):
        _ts(rep, "body.json", f"/measurements/{i}/t", m["t"], horizon)
        lo, hi = BODY_RANGES.get(m["type"], (0, 1e9))
        if not (lo <= m["v"] <= hi):
            rep.err("body.json", f"/measurements/{i}/v", f"impossible {m['type']} {m['v']}")

    # load annotations
    for i, a in enumerate((data.get("load") or {}).get("annotations", [])):
        if a["workout_id"] not in workout_ids:
            rep.warn("load.json", f"/annotations/{i}/workout_id", f"workout {a['workout_id']!r} not (yet) in workouts.json")
    _dupes(rep, "load.json", (data.get("load") or {}).get("annotations", []), "id", "/annotations")

    # strength
    lib_ids = {x["id"] for x in load_exercise_library()["exercises"]}
    st = data.get("strength") or {}
    lib_ids |= {x["id"] for x in st.get("exercises", [])}
    groups = set(cfg["muscles"]["groups"])
    for i, x in enumerate(st.get("exercises", [])):
        for mg in x.get("primary", []) + x.get("secondary", []):
            if mg not in groups:
                rep.err("strength.json", f"/exercises/{i}", f"unknown muscle group {mg!r}")
    _dupes(rep, "strength.json", st.get("sessions", []), "id", "/sessions")
    for i, s in enumerate(st.get("sessions", [])):
        _ts(rep, "strength.json", f"/sessions/{i}/start", s["start"], horizon)
        for j, ex in enumerate(s.get("exercises", [])):
            if ex["exercise_id"] not in lib_ids:
                rep.err("strength.json", f"/sessions/{i}/exercises/{j}/exercise_id", f"unknown exercise {ex['exercise_id']!r}")
        if s.get("workout_id") and s["workout_id"] not in workout_ids:
            rep.warn("strength.json", f"/sessions/{i}/workout_id", "linked workout not (yet) in workouts.json")

    # nutrition
    nut = data.get("nutrition") or {}
    _dupes(rep, "nutrition.json", nut.get("meals", []), "id", "/meals")
    for i, m in enumerate(nut.get("meals", [])):
        _ts(rep, "nutrition.json", f"/meals/{i}/t", m["t"], horizon)
        for j, it in enumerate(m["items"]):
            for k in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"):
                v = it.get(k)
                if v is not None and (v < 0 or v > 10000):
                    rep.err("nutrition.json", f"/meals/{i}/items/{j}/{k}", f"impossible {k} {v}")

    # goals
    for i, g in enumerate((data.get("goals") or {}).get("goals", [])):
        if g["type"] not in ("streak", "habit") and g.get("target") is None and g.get("status", "active") == "active":
            rep.err("goals.json", f"/goals/{i}/target", "active goal needs a target")
        per = g.get("period") or {}
        if per.get("start") and per.get("end") and per["start"] > per["end"]:
            rep.err("goals.json", f"/goals/{i}/period", "period start after end")
    _dupes(rep, "goals.json", (data.get("goals") or {}).get("goals", []), "id", "/goals")

    # plans
    pl = data.get("plans") or {}
    _dupes(rep, "plans.json", pl.get("sessions", []), "id", "/sessions")
    for i, s in enumerate(pl.get("sessions", [])):
        if s.get("linked_workout_id") and s["linked_workout_id"] not in workout_ids:
            rep.warn("plans.json", f"/sessions/{i}/linked_workout_id", "linked workout not (yet) in workouts.json")
    for i, c in enumerate(pl.get("calendar", [])):
        s = _ts(rep, "plans.json", f"/calendar/{i}/start", c["start"], None)
        e = _ts(rep, "plans.json", f"/calendar/{i}/end", c["end"], None)
        if s and e and e < s:
            rep.err("plans.json", f"/calendar/{i}", "event end before start")

    # journal
    for i, s in enumerate((data.get("journal") or {}).get("activity_status", [])):
        if s.get("end") and s["end"] < s["start"]:
            rep.err("journal.json", f"/activity_status/{i}", "status end before start")


def validate_data(data_dir, build_date=None):
    """Full validation. Returns (Report, data)."""
    rep = Report()
    data, problems, warnings = load_all(data_dir)
    for p in problems:
        rep.errors.append(p)
    for w in warnings:
        rep.warn("", "/", w)
    schemas = _schemas()
    for dom, payload in data.items():
        errs = Validator(schemas[dom]).validate(payload)
        for e in errs:
            rep.err(_fname(dom), e.pointer, e.message)
    if rep.ok:
        semantic_checks(data, rep, build_date)
    return rep, data
