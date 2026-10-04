"""Goals, streaks, training-log totals and progress comparison."""

from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute import load as loadm
from agame.compute.ctx import mean
from agame.values import mv


def _sum_workouts(ctx, start, end, sport=None, field="distance_m"):
    total, n = 0.0, 0
    for d in tu.daterange(start, min(end, ctx.d)):
        for w in ctx.workouts_by_day.get(d, []):
            if sport and w["_family"] != sport and w["sport"] != sport:
                continue
            if field == "distance_m":
                v = w.get("distance_m")
            elif field == "duration_s":
                v = w["_dur"]
            elif field == "elevation_gain_m":
                v = w.get("elevation_gain_m")
            elif field == "kcal":
                v = w.get("active_kcal")
            elif field == "kj":
                v = (w.get("avg_power_w") or 0) * w["_dur"] / 1000.0 if w.get("avg_power_w") else None
            elif field == "load":
                v = loadm.session_load(ctx, w)["v"]
            elif field == "count":
                v = 1
            else:
                v = None
            if v is not None:
                total += v
                n += 1
    return total, n


def _period(ctx, g):
    p = g.get("period") or {"type": "week"}
    t = p["type"]
    if t in ("week", "month", "year"):
        return tu.period_bounds(ctx.d, t, ctx.week_start)
    s = tu.parse_date(p["start"]) if p.get("start") else (ctx.first_day or ctx.d)
    e = tu.parse_date(p["end"]) if p.get("end") else ctx.d
    return s, e


@metric("goals.streak", unit="weeks", method="weekly_streak.v1", inputs=["workouts"])
def weekly_streak(ctx):
    need = ctx.cfg["goals"]["streak_min_activities_per_week"]
    ws = tu.week_start(ctx.d, ctx.week_start)
    counts = defaultdict(int)
    for w in ctx.workouts:
        counts[tu.week_start(w["_date"], ctx.week_start)] += 1
    streak = 0
    cur = ws
    # current week counts only if already satisfied (it is not over yet)
    if counts.get(cur, 0) < need:
        cur -= timedelta(days=7)
    while counts.get(cur, 0) >= need:
        streak += 1
        cur -= timedelta(days=7)
    longest, run = 0, 0
    if counts:
        first = min(counts)
        c = first
        while c <= ws:
            if counts.get(c, 0) >= need:
                run += 1
                longest = max(longest, run)
            elif c != ws:
                run = 0
            c += timedelta(days=7)
    return {"current": streak, "longest": longest, "this_week_done": counts.get(ws, 0) >= need, "this_week_count": counts.get(ws, 0)}


def evaluate(ctx, g, extra):
    """Return a goal progress dict. extra: precomputed helpers (best efforts, e1rm, weight, nutrition)."""
    typ = g["type"]
    start, end = _period(ctx, g)
    total_days = max(1, (end - start).days + 1)
    elapsed = max(0, min(total_days, (min(ctx.d, end) - start).days + 1))
    frac = elapsed / total_days
    out = {"id": g["id"], "title": g["title"], "type": typ, "target": g.get("target"), "unit": g.get("unit"),
           "start": start.isoformat(), "end": end.isoformat(), "elapsed_frac": round(frac, 3),
           "partial": ctx.d < end, "direction": g.get("direction"), "status_label": None}
    actual = None
    field = {"distance": "distance_m", "time": "duration_s", "elevation": "elevation_gain_m", "calories": "kcal",
             "kilojoules": "kj", "load": "load", "sessions": "count"}.get(typ)
    if field:
        actual, n = _sum_workouts(ctx, start, end, g.get("sport"), field)
        if n == 0 and not any(dd in ctx.covered for dd in tu.daterange(start, min(end, ctx.d))):
            actual = None
    elif typ == "streak":
        st = extra["streak"]
        out.update({"actual": st["current"], "longest": st["longest"], "status_label": "active" if st["current"] else "start"})
        return out
    elif typ == "record":
        effs = extra["best_efforts"].get("run", {}).get(g.get("distance_m"), [])
        in_p = [e for e in effs if start.isoformat() <= e["date"] <= end.isoformat()]
        best = min((e["time_s"] for e in in_p), default=None)
        out["actual"] = best
        out["best_effort"] = in_p[0] if in_p else None
        if best is None:
            out["status_label"] = "no_effort"
        else:
            out["status_label"] = "done" if best <= g["target"] else ("behind" if ctx.d > end else "in_progress")
            out["gap_s"] = round(best - g["target"], 1)
        return out
    elif typ == "strength":
        e1 = extra["e1rm"].get(g.get("exercise_id"))
        out["actual"] = e1["value"] if e1 else None
        out["as_of"] = e1["date"] if e1 else None
        if e1:
            out["progress_pct"] = round(100 * e1["value"] / g["target"], 1)
            out["status_label"] = "done" if e1["value"] >= g["target"] else "in_progress"
        else:
            out["status_label"] = "no_data"
        return out
    elif typ == "body_weight":
        w = extra["weight"]
        traj = (w or {}).get("goal") or {}
        out["actual"] = (w or {}).get("current", {}).get("v")
        out["trajectory"] = traj
        out["status_label"] = traj.get("status") or ("no_data" if out["actual"] is None else "insufficient")
        out["progress_pct"] = traj.get("progress_pct")
        return out
    elif typ == "nutrition":
        nut = extra["nutrition"]
        days = nut.get("days", [])
        metric_key = g.get("metric") or "protein_g"
        in_p = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat() and d.get(metric_key) is not None and d.get("complete") is not False]
        if not in_p:
            out.update({"actual": None, "status_label": "not_logged", "days_logged": 0})
            return out
        hit = sum(1 for d in in_p if d[metric_key] >= g["target"])
        out.update({"actual": round(mean([d[metric_key] for d in in_p]), 1), "days_hit": hit, "days_logged": len(in_p),
                    "adherence_pct": round(100 * hit / len(in_p)), "status_label": "on_track" if hit / len(in_p) >= 0.8 else "behind"})
        return out
    elif typ == "habit":
        n = sum(1 for e in (ctx.data.get("journal") or {}).get("entries", [])
                if e.get("habit_id") == g.get("metric") and start.isoformat() <= e["date"] <= end.isoformat())
        actual = n
    elif typ == "segment":
        out["actual"] = None
        out["status_label"] = "no_data"
        return out
    out["actual"] = actual
    tgt = g.get("target")
    if actual is None or tgt in (None, 0):
        out["status_label"] = "no_data"
        return out
    out["progress_pct"] = round(100.0 * actual / tgt, 1)
    out["expected_now"] = round(tgt * frac, 1)
    out["projected"] = round(actual / frac, 1) if frac > 0 else None
    if actual >= tgt:
        out["status_label"] = "done"
    elif frac == 0:
        out["status_label"] = "in_progress"
    else:
        ratio = actual / (tgt * frac)
        out["status_label"] = "ahead" if ratio >= 1.1 else ("on_track" if ratio >= 0.95 else "behind")
    return out


@metric("goals.progress", method="goal_progress.v1", inputs=["goals", "workouts", "body", "nutrition", "strength"])
def all_goals(ctx, extra):
    out = []
    for g in (ctx.data.get("goals") or {}).get("goals", []):
        if g.get("status", "active") == "archived":
            continue
        out.append(evaluate(ctx, g, extra))
    return out


# ----------------------------------------------------------------- training log
FIELDS = ("distance_m", "duration_s", "elevation_gain_m", "load", "count")


def _totals(ctx, start, end):
    fams = defaultdict(lambda: {k: 0.0 for k in FIELDS})
    for d in tu.daterange(start, min(end, ctx.d)):
        for w in ctx.workouts_by_day.get(d, []):
            f = fams[w["_family"]]
            f["distance_m"] += w.get("distance_m") or 0
            f["duration_s"] += w["_dur"]
            f["elevation_gain_m"] += w.get("elevation_gain_m") or 0
            sl = loadm.session_load(ctx, w)["v"]
            f["load"] += sl or 0
            f["count"] += 1
    allf = {k: sum(f[k] for f in fams.values()) for k in FIELDS}
    return {"all": allf, **{k: dict(v) for k, v in fams.items()}}


@metric("training.log", method="period_totals.v1", inputs=["workouts", "load.session"])
def training_log(ctx):
    out = {}
    for kind in ("week", "month", "quarter", "year"):
        s, e = tu.period_bounds(ctx.d, kind, ctx.week_start)
        ps, pe = tu.previous_period(s, e, kind, ctx.week_start)
        ly_s, ly_e = tu.same_period_last_year(s, e)
        # compare like-for-like elapsed portion
        elapsed = (ctx.d - s).days
        cur = _totals(ctx, s, e)
        prev_same = _totals(ctx, ps, min(pe, ps + timedelta(days=elapsed)))
        prev_full = _totals(ctx, ps, pe)
        ly = _totals(ctx, ly_s, min(ly_e, ly_s + timedelta(days=elapsed)))
        has_ly = ctx.first_day is not None and ctx.first_day <= ly_s
        out[kind] = {"start": s.isoformat(), "end": e.isoformat(), "partial": ctx.d < e, "totals": cur,
                     "prev_to_date": prev_same, "prev_full": prev_full, "prev_start": ps.isoformat(), "prev_end": pe.isoformat(),
                     "last_year_to_date": ly if has_ly else None}
    # weekly calendar rows (last 16 weeks) for the Strava-style log
    cur_ws = tu.week_start(ctx.d, ctx.week_start)
    weeks = []
    for i in range(15, -1, -1):
        ws = cur_ws - timedelta(days=7 * i)
        days = []
        for k in range(7):
            d = ws + timedelta(days=k)
            acts = []
            for w in ctx.workouts_by_day.get(d, []):
                sl = loadm.session_load(ctx, w)
                acts.append({"id": w["source_id"], "family": w["_family"], "sport": w["sport"], "distance_m": w.get("distance_m"),
                             "duration_s": round(w["_dur"]), "load": sl["v"], "name": w.get("name")})
            days.append({"date": d.isoformat(), "acts": acts, "future": d > ctx.d, "known": d in ctx.covered})
        t = _totals(ctx, ws, ws + timedelta(days=6))
        weeks.append({"week": ws.isoformat(), "days": days, "totals": t["all"], "by_family": {k: v for k, v in t.items() if k != "all"}})
    out["weeks"] = weeks
    # monthly series for 24 months
    months = []
    m = ctx.d.replace(day=1)
    for i in range(23, -1, -1):
        y, mo = m.year, m.month - i
        while mo <= 0:
            mo += 12
            y -= 1
        s = m.replace(year=y, month=mo, day=1)
        _, e = tu.period_bounds(s, "month")
        if ctx.first_day and e < ctx.first_day:
            continue
        t = _totals(ctx, s, e)
        months.append({"month": s.isoformat()[:7], "totals": t["all"], "run": t.get("run")})
    out["months"] = months
    return out


@metric("training.progress", method="period_vs_prior.v1", inputs=["workouts"])
def progress(ctx):
    """Strava-style Progress: cumulative weekly series for the current vs prior equal period (per range)."""
    out = {}
    for label, weeks in (("1m", 4), ("3m", 13), ("6m", 26), ("12m", 52)):
        cur_ws = tu.week_start(ctx.d, ctx.week_start)
        start = cur_ws - timedelta(days=7 * (weeks - 1))
        pstart = start - timedelta(days=7 * weeks)
        series = {}
        for fam in ("all", "run", "ride", "walk", "strength", "swim"):
            cur, prev = [], []
            for i in range(weeks):
                ws = start + timedelta(days=7 * i)
                pws = pstart + timedelta(days=7 * i)
                a = _totals(ctx, ws, ws + timedelta(days=6)).get(fam) or {k: 0.0 for k in FIELDS}
                b = _totals(ctx, pws, pws + timedelta(days=6)).get(fam) or {k: 0.0 for k in FIELDS}
                cur.append({"week": ws.isoformat(), **{k: round(a[k], 1) for k in FIELDS}})
                prev.append({"week": pws.isoformat(), **{k: round(b[k], 1) for k in FIELDS}})
            tot = {k: round(sum(r[k] for r in cur), 1) for k in FIELDS}
            ptot = {k: round(sum(r[k] for r in prev), 1) for k in FIELDS}
            if tot["count"] == 0 and ptot["count"] == 0:
                continue
            delta = {k: (round(100.0 * (tot[k] - ptot[k]) / ptot[k], 1) if ptot[k] else None) for k in FIELDS}
            series[fam] = {"current": cur, "prior": prev, "total": tot, "prior_total": ptot, "delta_pct": delta}
        has_prior = ctx.first_day is not None and ctx.first_day <= pstart
        out[label] = {"start": start.isoformat(), "prior_start": pstart.isoformat(), "weeks": weeks, "series": series, "prior_complete": has_prior}
    return out
