"""Strain (day + workout), Stress (estimate) and Energy Bank."""

import math
from datetime import datetime, time, timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import clamp, mean, percentile
from agame.compute import load as loadm
from agame.values import mv


def _workout_windows(ctx, d):
    return [(w["_start"], w["_end"]) for w in ctx.workouts_by_day.get(d, [])]


def _in_any(dt, windows):
    return any(s <= dt <= e for s, e in windows)


def raw_day_strain(ctx, d):
    """Return (raw TRIMP-like load, method) or (None, None). Workouts + non-workout elevated HR."""
    if d not in ctx.covered:
        return None, None
    total = 0.0
    for w in ctx.workouts_by_day.get(d, []):
        sl = loadm.session_load(ctx, w)
        if sl["v"] is not None:
            total += sl["v"]
    method = "workouts_only"
    hrmax, (hrrest, _) = ctx.phys("hr_max"), loadm.resting_hr(ctx, d)
    pts = ctx.by_day("heart_rate_bpm").get(d, [])
    if pts and hrmax and hrrest:
        floor = hrrest + ctx.cfg["strain"]["hr_floor_pct_reserve"] * (hrmax - hrrest)
        wins = _workout_windows(ctx, d)
        k, _ = loadm._trimp_k(ctx)
        extra = 0.0
        for i in range(1, len(pts)):
            dt = min(600, (pts[i][0] - pts[i - 1][0]).total_seconds())
            hr = (pts[i][1] + pts[i - 1][1]) / 2
            if hr > floor and not _in_any(pts[i][0], wins):
                extra += loadm.trimp_from_avg(hr, dt / 60.0, hrmax, hrrest, k)
        total += extra
        method = "workouts_plus_daytime_hr"
    return total, method


def _k(ctx):
    if hasattr(ctx, "_strain_k"):
        return ctx._strain_k
    cfg = ctx.cfg["strain"]
    raws = []
    for i in range(90):
        r, _ = raw_day_strain(ctx, ctx.d - timedelta(days=i))
        if r is not None:
            raws.append(r)
    if len(raws) >= cfg["personal_k_min_days"]:
        p90 = percentile(raws, 90)
        k = (p90 / math.log(10)) if p90 and p90 > 0 else cfg["default_k"]
        res = (k, "personal_p90")
    else:
        res = (cfg["default_k"], "default")
    ctx._strain_k = res
    return res


def strain_pct(ctx, raw):
    k, _ = _k(ctx)
    return 100.0 * (1 - math.exp(-raw / k))


@metric("strain.day", unit="%", method="strain_saturating.v1", inputs=["load.session", "metrics.heart_rate_bpm"])
def day_strain_series(ctx, days=365):
    out = {}
    methods = {}
    for i in range(days):
        d = ctx.d - timedelta(days=i)
        r, m = raw_day_strain(ctx, d)
        if r is not None:
            out[d] = round(strain_pct(ctx, r), 1)
            methods[d] = m
    return out, methods


@metric("strain.workout", unit="%", method="strain_saturating.v1", inputs=["load.session"])
def workout_strain(ctx, w):
    sl = loadm.session_load(ctx, w)
    if sl["v"] is None:
        return None
    return round(strain_pct(ctx, sl["v"]), 1)


def strain_summary(ctx):
    cfg = ctx.cfg["strain"]
    series, methods = day_strain_series(ctx)
    k, kh = _k(ctx)
    last60 = [v for d, v in series.items() if (ctx.d - d).days < 60]
    nr = None
    if len(last60) >= 14:
        lo, hi = cfg["normal_range_pct"]
        nr = {"low": round(percentile(last60, lo)), "high": round(percentile(last60, hi))}
    today = series.get(ctx.d)
    m = methods.get(ctx.d)
    exercise_min = sum(w["_dur"] for w in ctx.workouts_by_day.get(ctx.d, [])) / 60.0
    hr_today = [v for _, v in ctx.by_day("heart_rate_bpm").get(ctx.d, [])]
    sc = mv(today, "%", method="strain_saturating.v1", as_of=ctx.local_iso(ctx.now) if today is not None else None,
            status=None if today is None else ("partial" if m == "workouts_only" else "ok"),
            note=("So far today · workouts only (no daytime heart rate)" if m == "workouts_only" else "So far today"), k=round(k, 1), k_method=kh,
            yesterday=series.get(ctx.d - timedelta(days=1)))
    hist = [{"date": d.isoformat(), "v": v} for d, v in sorted(series.items())]
    return {"score": sc, "history": hist, "normal_range": nr, "by_day": series,
            "exercise_min": round(exercise_min), "daytime_hr": round(mean(hr_today)) if hr_today else None}


# ----------------------------------------------------------------- stress (estimate)
@metric("stress.day", unit="%", method="stress_hr_reserve.v1", inputs=["metrics.heart_rate_bpm", "metrics.resting_hr_bpm"])
def stress_for(ctx, d):
    cfg = ctx.cfg["stress"]
    hrmax, (hrrest, _) = ctx.phys("hr_max"), loadm.resting_hr(ctx, d)
    if not hrmax or not hrrest:
        return None
    from agame.compute import sleep as sleepm
    nights, _ = sleepm.nights_by_date(ctx)
    sleep_windows = []
    for dd in (d, d + timedelta(days=1)):
        nm = nights.get(dd)
        if nm:
            sleep_windows.append((tu.parse_ts(nm["start"]), tu.parse_ts(nm["end"])))
    wins = _workout_windows(ctx, d) + [(s - timedelta(minutes=30), e + timedelta(minutes=60)) for s, e in _workout_windows(ctx, d)]
    hours = {}
    for dt, v in ctx.by_day("heart_rate_bpm").get(d, []):
        if not (cfg["day_start_hour"] <= dt.hour < cfg["day_end_hour"]):
            continue
        if _in_any(dt, wins) or _in_any(dt, sleep_windows):
            continue
        hours.setdefault(dt.hour, []).append(v)
    good = {h: vs for h, vs in hours.items() if len(vs) >= cfg["min_samples_per_hour"]}
    if len(good) < cfg["min_daytime_hours"]:
        return None
    span = cfg["reserve_fraction_for_100"] * (hrmax - hrrest)
    hourly = [{"hour": h, "v": round(clamp(100 * (mean(vs) - hrrest) / span, 0, 100))} for h, vs in sorted(good.items())]
    vals = [x["v"] for x in hourly]
    return {"date": d.isoformat(), "hourly": hourly, "avg": round(mean(vals)), "high": max(vals), "low": min(vals), "hours": len(hourly)}


def stress_summary(ctx):
    days = []
    for i in range(60):
        s = stress_for(ctx, ctx.d - timedelta(days=i))
        if s:
            days.append(s)
    days.sort(key=lambda s: s["date"])
    latest = days[-1] if days else None
    sc = mv(latest["avg"] if latest else None, "%", kind="estimated", method="stress_hr_reserve.v1",
            as_of=ctx.series_as_of("heart_rate_bpm") if latest else None,
            status=None if not latest else ("ok" if latest["date"] == ctx.d.isoformat() else "stale"),
            note=None if latest else "Not enough daytime heart-rate samples", date=latest["date"] if latest else None)
    return {"score": sc, "latest": latest, "history": [{"date": s["date"], "avg": s["avg"], "high": s["high"], "low": s["low"]} for s in days]}


# ----------------------------------------------------------------- energy bank
@metric("energy.bank", unit="%", method="energy_bank.v1", inputs=["recovery.score", "sleep.score", "strain.workout", "stress.day"])
def energy_bank(ctx, d, recovery_score, sleep_score, stress_day):
    cfg = ctx.cfg["energy"]
    parts = []
    sw = cfg["start_weights"]
    if recovery_score is not None:
        parts.append((recovery_score, sw["recovery"]))
    if sleep_score is not None:
        parts.append((sleep_score, sw["sleep"]))
    if not parts:
        return None
    start_val = sum(v * w for v, w in parts) / sum(w for _, w in parts)
    from agame.compute import sleep as sleepm
    nights, _ = sleepm.nights_by_date(ctx)
    nm = nights.get(d)
    wake = tu.parse_ts(nm["wake"]).astimezone(ctx.tz) if nm else datetime.combine(d, time(6, 30), tzinfo=ctx.tz)
    samples = [dt for dt, _ in ctx.by_day("heart_rate_bpm").get(d, [])]
    ends = samples + [w["_end"] for w in ctx.workouts_by_day.get(d, [])]
    last = max(ends) if ends else wake
    if last < wake:
        last = wake
    stress_by_hour = {h["hour"]: h["v"] for h in (stress_day or {}).get("hourly", [])}
    curve = [{"t": wake.isoformat(), "v": round(start_val)}]
    level = start_val
    t = wake
    while t < last:
        nt = min(last, t + timedelta(hours=1))
        frac = (nt - t).total_seconds() / 3600.0
        drain = cfg["baseline_drain_per_hour"] * frac
        s = stress_by_hour.get(t.hour)
        if s is not None and s > 50:
            drain += cfg["stress_drain_per_hour_above_50"] * frac * (s - 50) / 10.0
        for w in ctx.workouts_by_day.get(d, []):
            ov = (min(nt, w["_end"]) - max(t, w["_start"])).total_seconds()
            if ov > 0:
                ws = workout_strain(ctx, w)
                if ws is not None:
                    drain += cfg["workout_drain_per_strain_pct"] * ws * ov / max(1.0, w["_dur"])
        level = clamp(level - drain, 0, 100)
        curve.append({"t": nt.isoformat(), "v": round(level)})
        t = nt
    return {"start": round(start_val), "current": round(level), "as_of": last.isoformat(), "curve": curve}
