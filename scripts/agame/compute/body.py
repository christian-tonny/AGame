"""Body weight trajectory, VO2 max trend, and generic metric trends."""

from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import linreg, mean, median
from agame.values import mv


def _measurements(ctx, mtype):
    out = []
    for m in (ctx.data.get("body") or {}).get("measurements", []):
        if m["type"] != mtype:
            continue
        dt = tu.local_dt(m["t"], ctx.tz)
        if dt > ctx.now:
            continue
        out.append((dt, dt.date(), m["v"], m))
    out.sort(key=lambda r: (r[0], r[3]["source_id"]))
    return out


def weight_goal(ctx):
    for g in (ctx.data.get("goals") or {}).get("goals", []):
        if g["type"] == "body_weight" and g.get("status", "active") == "active":
            return g
    return None


@metric("body.weight", unit="kg", method="weekly_median_trend.v1", inputs=["body.weight_kg", "goals.body_weight"])
def weight_summary(ctx):
    cfg = ctx.cfg["body"]
    pts = _measurements(ctx, "weight_kg")
    if not pts:
        return {"status": "missing", "current": mv(None, "kg", note="No weigh-ins yet", kind="observed"), "points": [], "weekly": []}
    daily = {}
    for dt, dd, v, m in pts:
        daily.setdefault(dd, []).append(v)
    daily = {d: median(vs) for d, vs in daily.items()}
    weeks = defaultdict(list)
    for d, v in daily.items():
        weeks[tu.week_start(d, ctx.week_start)].append(v)
    cur_ws = tu.week_start(ctx.d, ctx.week_start)
    weekly = [{"week": ws.isoformat(), "median": round(median(vs), 2), "n": len(vs), "partial": ws == cur_ws} for ws, vs in sorted(weeks.items())]
    # trend over last N days
    cutoff = ctx.d - timedelta(days=cfg["trend_days"])
    recent = sorted((d, v) for d, v in daily.items() if d > cutoff)
    slope = None
    status = "ok"
    if len(recent) >= cfg["trend_min_points"] and (recent[-1][0] - recent[0][0]).days >= cfg["trend_min_span_days"]:
        s, _ = linreg([d.toordinal() for d, _ in recent], [v for _, v in recent])
        slope = s * 7 if s is not None else None
    else:
        status = "insufficient"
    # current = last 7-day median (or latest week median)
    last7 = [v for d, v in daily.items() if (ctx.d - d).days < 7]
    current = median(last7) if last7 else weekly[-1]["median"]
    cur_as_of = pts[-1][3]["t"]
    stale = (ctx.d - pts[-1][1]).days > 7
    out = {
        "status": status,
        "current": mv(round(current, 1), "kg", kind="computed", method="7_day_median", as_of=cur_as_of, status="stale" if stale else "ok",
                      latest=pts[-1][2], latest_date=pts[-1][1].isoformat()),
        "trend_kg_per_week": mv(round(slope, 2) if slope is not None else None, "kg/week", method="ols_28d",
                                note=None if slope is not None else f"Need {cfg['trend_min_points']} weigh-ins over {cfg['trend_min_span_days']} days (have {len(recent)})"),
        "points": [{"date": d.isoformat(), "v": round(v, 2)} for d, v in sorted(daily.items()) if (ctx.d - d).days <= 730],
        "weekly": weekly[-104:],
        "weigh_ins_28d": len(recent),
    }
    g = weight_goal(ctx)
    if g and g.get("target") is not None:
        out["goal"] = trajectory(ctx, g, current, slope, cfg)
    else:
        out["goal"] = None
    comp = {}
    for mtype in ("body_fat_pct", "lean_mass_kg", "waist_cm"):
        mp = _measurements(ctx, mtype)
        if mp:
            comp[mtype] = {"current": mp[-1][2], "as_of": mp[-1][3]["t"], "points": [{"date": dd.isoformat(), "v": v} for _, dd, v, _ in mp[-200:]]}
    out["composition"] = comp
    return out


def trajectory(ctx, g, current, slope, cfg):
    target = g["target"]
    end = tu.parse_date((g.get("period") or {}).get("end")) if (g.get("period") or {}).get("end") else None
    direction = g.get("direction") or ("decrease" if target < current else "increase")
    remaining = target - current
    out = {"target": target, "target_date": end.isoformat() if end else None, "remaining_kg": round(remaining, 1), "direction": direction}
    if end:
        weeks_left = max(0.0, (end - ctx.d).days / 7.0)
        out["weeks_left"] = round(weeks_left, 1)
        out["required_kg_per_week"] = round(remaining / weeks_left, 3) if weeks_left > 0 else None
    if slope is not None:
        out["actual_kg_per_week"] = round(slope, 3)
        moving_toward = (slope < 0 and remaining < 0) or (slope > 0 and remaining > 0)
        if abs(remaining) < 0.3:
            out["status"] = "done"
        elif moving_toward and abs(slope) > 1e-6:
            weeks = remaining / slope
            out["projected_date"] = (ctx.d + timedelta(days=round(weeks * 7))).isoformat()
            req = out.get("required_kg_per_week")
            if req is None:
                out["status"] = "behind"
            elif abs(slope) >= abs(req) * cfg["ahead_ratio"]:
                out["status"] = "ahead"
            elif abs(slope) >= abs(req):
                out["status"] = "on_track"
            else:
                out["status"] = "behind"
        else:
            out["status"] = "behind"
            out["projected_date"] = None
    else:
        out["status"] = "insufficient"
    if g.get("start_value") is not None and (g["start_value"] - target) != 0:
        out["progress_pct"] = round(100 * (g["start_value"] - current) / (g["start_value"] - target), 1)
    return out


def _smooth(points, days):
    """Rolling mean of raw points within ±days (by date ordinal)."""
    out = []
    for i, (d, _) in enumerate(points):
        vals = [v for dd, v in points if abs((dd - d).days) <= days]
        out.append((d, sum(vals) / len(vals)))
    return out


@metric("body.vo2max", unit="ml/kg/min", method="vo2max_raw_plus_rolling_mean.v1", inputs=["metrics.vo2max_ml_kg_min"])
def vo2_summary(ctx):
    cfg = ctx.cfg["body"]
    raw = [(dd, v, (dt.isoformat() if dt else None)) for dt, dd, v, _ in ctx.series("vo2max_ml_kg_min")]
    if not raw:
        return {"status": "missing", "current": mv(None, "ml/kg/min", kind="observed", note="No cardio-fitness samples yet"), "points": [], "smoothed": []}
    pts = [(d, v) for d, v, _ in raw]
    sm = _smooth(pts, cfg["vo2_smoothing_days"])
    smd = dict(sm)

    def at(days_ago):
        target = ctx.d - timedelta(days=days_ago)
        cands = [(abs((d - target).days), v) for d, v in sm if abs((d - target).days) <= 7]
        return min(cands)[1] if cands else None

    cur_s = sm[-1][1]
    d30, d90 = at(30), at(90)
    n90 = sum(1 for d, _ in pts if (ctx.d - d).days <= 90)
    c = cfg["vo2_confidence"]
    confidence = "high" if n90 >= c["high"] else ("medium" if n90 >= c["medium"] else "low")
    gaps = []
    for i in range(1, len(pts)):
        if (pts[i][0] - pts[i - 1][0]).days > cfg["vo2_gap_days"]:
            gaps.append({"from": pts[i - 1][0].isoformat(), "to": pts[i][0].isoformat(), "days": (pts[i][0] - pts[i - 1][0]).days})
    stale = (ctx.d - pts[-1][0]).days > 30
    return {
        "status": "stale" if stale else "ok",
        "current": mv(round(pts[-1][1], 1), "ml/kg/min", kind="observed", as_of=raw[-1][2] or pts[-1][0].isoformat(),
                      status="stale" if stale else "ok", source="HealthKit cardio fitness"),
        "smoothed_current": round(cur_s, 1),
        "delta_30": round(cur_s - d30, 1) if d30 is not None else None,
        "delta_90": round(cur_s - d90, 1) if d90 is not None else None,
        "confidence": confidence, "samples_90d": n90, "gaps": gaps,
        "points": [{"date": d.isoformat(), "v": round(v, 1)} for d, v in pts],
        "smoothed": [{"date": d.isoformat(), "v": round(v, 2)} for d, v in sm],
    }


@metric("metrics.trend", method="daily_agg_trend.v1", inputs=["metrics.*"])
def metric_trend(ctx, sid, days=730):
    meta = ctx.series_meta(sid)
    daily = ctx.daily(sid)
    rows = sorted((d, v) for d, v in daily.items() if (ctx.d - d).days <= days)
    if not rows:
        return None
    last7 = [v for d, v in rows if (ctx.d - d).days < 7]
    prev = [v for d, v in rows if 7 <= (ctx.d - d).days < 35]
    return {
        "id": sid, "label": meta.get("label", sid), "unit": meta.get("unit"), "agg": meta.get("agg", "mean"), "better": meta.get("better"),
        "points": [{"date": d.isoformat(), "v": round(v, 2)} for d, v in rows],
        "latest": round(rows[-1][1], 2), "latest_date": rows[-1][0].isoformat(), "as_of": ctx.series_as_of(sid),
        "avg_7": round(mean(last7), 2) if last7 else None, "avg_prev_28": round(mean(prev), 2) if prev else None,
        "n": len(rows),
    }


def all_metric_trends(ctx):
    out = {}
    for sid in ctx.series_ids():
        if ctx.series_meta(sid).get("intraday"):
            continue
        t = metric_trend(ctx, sid)
        if t:
            out[sid] = t
    return out
