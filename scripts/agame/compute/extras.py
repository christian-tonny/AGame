"""Biological Age, timeline, journal, health records, social, recaps, weekly review,
widgets and the data-status (freshness) block."""

import math
from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute import load as loadm
from agame.compute.ctx import clamp, mean, median
from agame.values import mv


# ----------------------------------------------------------------- PhenoAge (Levine 2018)
PHENO_CODES = ("albumin", "creatinine", "glucose", "crp", "lymphocyte_pct", "mcv", "rdw", "alp", "wbc")


def _hm(minutes):
    m = round(minutes)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def _to_unit(code, value, unit):
    u = (unit or "").lower().replace(" ", "")
    if code == "albumin":
        return value * 10 if u in ("g/dl",) else value  # -> g/L
    if code == "creatinine":
        return value * 88.42 if u in ("mg/dl",) else value  # -> umol/L
    if code == "glucose":
        return value / 18.016 if u in ("mg/dl",) else value  # -> mmol/L
    if code == "crp":
        return value / 10.0 if u in ("mg/l",) else value  # -> mg/dL
    return value


def phenoage(age, m):
    """Levine et al. 2018 Phenotypic Age. m: dict of the nine markers in canonical units:
    albumin g/L, creatinine umol/L, glucose mmol/L, crp mg/dL, lymphocyte %, MCV fL, RDW %, ALP U/L, WBC 10^3/uL."""
    xb = (-19.907 - 0.0336 * m["albumin"] + 0.0095 * m["creatinine"] + 0.1953 * m["glucose"]
          + 0.0954 * math.log(max(m["crp"], 1e-3)) - 0.0120 * m["lymphocyte_pct"] + 0.0268 * m["mcv"]
          + 0.3306 * m["rdw"] + 0.00188 * m["alp"] + 0.0554 * m["wbc"] + 0.0804 * age)
    gamma = 0.0076927
    mort = 1 - math.exp(-math.exp(xb) * (math.exp(120 * gamma) - 1) / gamma)
    mort = min(max(mort, 1e-12), 1 - 1e-12)
    return 141.50225 + math.log(-0.00553 * math.log(1 - mort)) / 0.090165


def _latest_biomarkers(ctx, as_of):
    latest = {}
    for r in (ctx.data.get("health_records") or {}).get("records", []):
        if tu.parse_date(r["date"]) > as_of:
            continue
        for b in r.get("biomarkers") or []:
            code = (b.get("code") or b["name"]).lower()
            if code not in latest or r["date"] >= latest[code][0]:
                latest[code] = (r["date"], _to_unit(code, b["value"], b["unit"]))
    return latest


@metric("bioage.estimate", unit="years", method="agame_bioage.v1 (+ PhenoAge when 9 biomarkers)",
        inputs=["profile.birth_year", "sleep", "metrics.steps", "workouts.zones", "strength", "health_records"])
def bioage(ctx, sleep_hist):
    bcfg = ctx.cfg["bioage"]
    by = (ctx.profile.get("athlete") or {}).get("birth_year")
    monday = ctx.d - timedelta(days=ctx.d.weekday())
    next_update = (monday + timedelta(days=7) - ctx.d).days

    def at(m):
        w0, w1 = m - timedelta(days=bcfg["window_days"]), m - timedelta(days=1)
        need, have = [], {}
        if not by:
            need.append("Birth year (profile)")
        sleeps = [h for h in sleep_hist if w0.isoformat() <= h["date"] <= w1.isoformat() and h["asleep_min"]]
        if len(sleeps) < bcfg["min_coverage_days"]:
            need.append(f"Sleep on {bcfg['min_coverage_days']}+ of the last {bcfg['window_days']} nights (have {len(sleeps)})")
        steps = [v for d, v in ctx.daily("steps").items() if w0 <= d <= w1]
        if len(steps) < bcfg["min_coverage_days"]:
            need.append(f"Steps on {bcfg['min_coverage_days']}+ days (have {len(steps)})")
        hz = loadm.hr_zones(ctx)
        if not hz.get("zones"):
            need.append("HR zones (configure HR max)")
        if need:
            return None, need
        chrono = m.year - by - (0.5)
        refs = bcfg["references"]
        cap = bcfg["max_category_delta_years"]
        cats = {}
        sl = mean([h["asleep_min"] for h in sleeps])
        mids = [h["midpoint_min"] for h in sleeps if h.get("midpoint_min") is not None]
        sd = (math.sqrt(sum((x - mean(mids)) ** 2 for x in mids) / (len(mids) - 1)) if len(mids) > 1 else None)
        sdelta = (refs["sleep_min"] - sl) / 30.0 * (0.5 if sl < refs["sleep_min"] else 0.25)
        if sd is not None:
            sdelta += (sd - refs["sleep_regularity_sd_min"]) / 30.0 * 0.5
        cats["sleep"] = {"label": "Sleep", "delta_years": round(clamp(sdelta, -cap, cap), 1), "inputs": {"avg_sleep_min": round(sl), "midpoint_sd_min": round(sd) if sd else None}}
        z23 = z45 = strength_min = 0.0
        for w in ctx.workouts:
            if w0 <= w["_date"] <= w1:
                z = loadm.workout_zones(ctx, w)
                if z:
                    z23 += sum(x["s"] for x in z[1:3]) / 60.0
                    z45 += sum(x["s"] for x in z[3:]) / 60.0
                if w["_family"] == "strength":
                    strength_min += w["_dur"] / 60.0
        weeks = bcfg["window_days"] / 7.0
        z23w, z45w, strw = z23 / weeks, z45 / weeks, strength_min / weeks
        st = mean(steps)
        adelta = (refs["steps"] - st) / 2000.0 * 0.5 + (refs["zone23_min_week"] - z23w) / refs["zone23_min_week"] * 1.0 \
            + (refs["zone45_min_week"] - z45w) / refs["zone45_min_week"] * 0.5 + (refs["strength_min_week"] - strw) / refs["strength_min_week"] * 0.75
        cats["activity"] = {"label": "Activity", "delta_years": round(clamp(adelta, -cap, cap), 1),
                            "inputs": {"steps": round(st), "zone2_3_min_week": round(z23w), "zone4_5_min_week": round(z45w), "strength_min_week": round(strw)}}
        if refs.get("vo2max"):
            v = [val for d, val in ctx.daily("vo2max_ml_kg_min").items() if d <= w1]
            if v:
                cats["fitness"] = {"label": "Fitness", "delta_years": round(clamp((refs["vo2max"] - v[-1]) / 3.0 * 0.5, -cap, cap), 1), "inputs": {"vo2max": v[-1]}}
        bm = _latest_biomarkers(ctx, w1)
        blood_missing = [c for c in PHENO_CODES if c not in bm]
        if not blood_missing:
            pa = phenoage(chrono, {c: bm[c][1] for c in PHENO_CODES})
            cats["blood"] = {"label": "Blood", "delta_years": round(clamp((pa - chrono) * bcfg["phenoage_weight"], -cap * 2, cap * 2), 1),
                             "inputs": {"phenoage": round(pa, 1), "labs_date": max(bm[c][0] for c in PHENO_CODES)}}
        total = chrono + sum(c["delta_years"] for c in cats.values())
        cov = mean([min(1, len(sleeps) / bcfg["window_days"]), min(1, len(steps) / bcfg["window_days"])])
        conf = round(100 * cov * (1.0 if "blood" in cats else 0.85))
        return {"value": round(total, 1), "chronological": round(chrono, 1), "categories": cats, "confidence_pct": conf,
                "blood_missing": blood_missing, "as_of": m.isoformat()}, []

    cur, need = at(monday)
    if cur is None:
        return {"status": "missing", "needed": need, "next_update_days": next_update,
                "methodology": "AGame estimate from 30-day sleep, steps, zone time and strength time (+ Levine PhenoAge from 9 blood markers when available). Not a medical measure."}
    prev, _ = at(monday - timedelta(days=7))
    changes = []
    if prev:
        for k, c in cur["categories"].items():
            p = prev["categories"].get(k)
            if p:
                changes.append({"id": k, "label": c["label"], "delta": round(c["delta_years"] - p["delta_years"], 1)})
    return {"status": "ok", **cur, "vs_last_week": round(cur["value"] - prev["value"], 1) if prev else None, "this_week_changes": changes,
            "next_update_days": next_update, "kind": "estimated",
            "methodology": "AGame estimate from 30-day sleep, steps, zone time and strength time (+ Levine PhenoAge from 9 blood markers when available). Not a medical measure."}


# ----------------------------------------------------------------- health records
def health_records(ctx):
    recs = sorted((ctx.data.get("health_records") or {}).get("records", []), key=lambda r: r["date"], reverse=True)
    trends = defaultdict(list)
    for r in recs:
        for b in r.get("biomarkers") or []:
            key = (b.get("code") or b["name"]).lower()
            trends[key].append({"date": r["date"], "value": b["value"], "unit": b["unit"], "name": b["name"],
                                "ref_low": b.get("ref_low"), "ref_high": b.get("ref_high"), "ref_text": b.get("ref_text")})
    for k in trends:
        trends[k].sort(key=lambda x: x["date"])
    return {"records": [{k: v for k, v in r.items() if k != "text"} | {"has_text": bool(r.get("text"))} for r in recs], "biomarkers": dict(trends),
            "enabled": (ctx.profile.get("modules") or {}).get("health_records", True)}


# ----------------------------------------------------------------- journal / status / cycle
def journal(ctx):
    j = ctx.data.get("journal") or {}
    entries = sorted(j.get("entries", []), key=lambda e: (e["date"], e.get("t") or ""), reverse=True)
    status = ctx.status_on(ctx.d)
    cyc = None
    if (ctx.profile.get("modules") or {}).get("cycle_tracking"):
        logs = sorted(j.get("cycle", []), key=lambda c: c["date"])
        cyc = {"enabled": True, "logs": logs[-120:], "latest": logs[-1] if logs else None}
    return {"entries": entries[:300], "habits": j.get("habits", []), "status": status,
            "status_history": sorted(j.get("activity_status", []), key=lambda s: s["start"], reverse=True), "cycle": cyc or {"enabled": False}}


# ----------------------------------------------------------------- timeline
def timeline(ctx, sleep_block, recovery_hist, days=14):
    out = {}
    nights = {h["date"]: h for h in sleep_block.get("history", [])}
    rec_by = {h["date"]: h["score"] for h in recovery_hist}
    meals = (ctx.data.get("nutrition") or {}).get("meals", [])
    body = (ctx.data.get("body") or {}).get("measurements", [])
    jentries = (ctx.data.get("journal") or {}).get("entries", [])
    events = (ctx.data.get("plans") or {}).get("calendar", [])
    sessions = (ctx.data.get("plans") or {}).get("sessions", [])
    for k in range(days):
        d = ctx.d - timedelta(days=k)
        ds = d.isoformat()
        items = []
        n = nights.get(ds)
        if n:
            items.append({"t": n["bed"], "type": "sleep", "title": "Sleep", "detail": f"{_hm(n['asleep_min'])} asleep" if n.get("asleep_min") is not None else "Time asleep not recorded", "score": n.get("score"),
                          "end": n["wake"]})
        if ds in rec_by:
            items.append({"t": n["wake"] if n else f"{ds}T06:00:00", "type": "score", "title": "Recovery", "detail": f"{rec_by[ds]}%"})
        for w in ctx.workouts_by_day.get(d, []):
            items.append({"t": w["_start"].isoformat(), "type": "workout", "title": w.get("name") or w["sport"], "id": w["source_id"],
                          "detail": _hm(w["_dur"] / 60) + (f" · {w['distance_m'] / 1000:.1f} km" if w.get("distance_m") else ""), "sport": w["sport"]})
        for m in meals:
            dt = tu.local_dt(m["t"], ctx.tz)
            if dt.date() == d and dt <= ctx.now:
                p = sum(it.get("protein_g") or 0 for it in m["items"])
                kc = sum(it.get("kcal") or 0 for it in m["items"])
                items.append({"t": dt.isoformat(), "type": "meal", "title": m.get("name") or (m.get("meal") or "Meal").title(), "id": m["id"],
                              "detail": f"{round(kc)} kcal · {round(p)} g protein"})
        for b in body:
            dt = tu.local_dt(b["t"], ctx.tz)
            if dt.date() == d and dt <= ctx.now:
                items.append({"t": dt.isoformat(), "type": "measurement", "title": {"weight_kg": "Weight", "body_fat_pct": "Body fat"}.get(b["type"], b["type"]),
                              "detail": f"{b['v']} {'kg' if b['type'].endswith('kg') else '%'}"})
        for e in jentries:
            if e["date"] == ds:
                items.append({"t": e.get("t") or f"{ds}T21:00:00", "type": "journal", "title": e["type"].replace("_", " ").title(),
                              "detail": e.get("text") or (f"{e['value']:g} {e.get('unit') or ''}".strip() if e.get("value") is not None else None)})
        for e in events:
            es = tu.local_dt(e["start"], ctx.tz)
            if es.date() == d:
                items.append({"t": es.isoformat(), "type": "event", "title": e["title"], "end": tu.local_dt(e["end"], ctx.tz).isoformat()})
        for s in sessions:
            if s["date"] == ds:
                items.append({"t": f"{ds}T{s.get('start_time') or '06:00'}:00", "type": "planned", "title": s.get("title") or s["type"], "detail": "Planned"})
        items.sort(key=lambda x: x["t"])
        out[ds] = items
    return out


# ----------------------------------------------------------------- social
def social(ctx, goals_progress):
    s = ctx.data.get("social") or {}
    own = [g for g in goals_progress if g["type"] in ("distance", "time", "elevation", "sessions") and g.get("start")]
    return {"connected": bool(s.get("connected")), "athletes": s.get("athletes", []), "clubs": s.get("clubs", []), "posts": s.get("posts", []),
            "kudos": s.get("kudos", []), "comments": s.get("comments", []), "challenges": s.get("challenges", []), "events": s.get("events", []),
            "own_challenges": own, "races": (ctx.data.get("plans") or {}).get("races", [])}


# ----------------------------------------------------------------- recaps
def _recap(ctx, start, end, label, sleep_hist, recovery_hist, weight_points):
    from agame.compute.activity import all_best_efforts
    ws = [w for w in ctx.workouts if start <= w["_date"] <= end]
    if not ws and not any(start.isoformat() <= h["date"] <= end.isoformat() for h in sleep_hist):
        return None
    fams = defaultdict(lambda: {"distance_m": 0.0, "duration_s": 0.0, "elevation_gain_m": 0.0, "count": 0, "load": 0.0})
    for w in ws:
        f = fams[w["_family"]]
        f["distance_m"] += w.get("distance_m") or 0
        f["duration_s"] += w["_dur"]
        f["elevation_gain_m"] += w.get("elevation_gain_m") or 0
        f["count"] += 1
        f["load"] += loadm.session_load(ctx, w)["v"] or 0
    longest = max((w for w in ws if w.get("distance_m")), key=lambda w: w["distance_m"], default=None)
    be = all_best_efforts(ctx).get("run", {})
    fastest = []
    for D, efforts in sorted(be.items()):
        inp = [e for e in efforts if start.isoformat() <= e["date"] <= end.isoformat()]
        if inp:
            prior_best = [e for e in efforts if e["date"] < start.isoformat()]
            fastest.append({"distance_m": D, "time_s": inp[0]["time_s"], "date": inp[0]["date"],
                            "pr": not prior_best or inp[0]["time_s"] < prior_best[0]["time_s"] if prior_best else True})
    weeks = {tu.week_start(w["_date"], ctx.week_start) for w in ws}
    total_weeks = len({tu.week_start(d, ctx.week_start) for d in tu.daterange(start, min(end, ctx.d))})
    months = defaultdict(lambda: {"load": 0.0, "count": 0, "active_days": set()})
    for w in ws:
        k = w["_date"].isoformat()[:7]
        months[k]["load"] += loadm.session_load(ctx, w)["v"] or 0
        months[k]["count"] += 1
        months[k]["active_days"].add(w["_date"])
    mrows = [{"month": k, "load": round(v["load"]), "count": v["count"], "active_days": len(v["active_days"])} for k, v in sorted(months.items())]
    sl = [h["asleep_min"] for h in sleep_hist if start.isoformat() <= h["date"] <= end.isoformat() and h["asleep_min"]]
    rc = [h["score"] for h in recovery_hist if start.isoformat() <= h["date"] <= end.isoformat()]
    wp = [p for p in weight_points if start.isoformat() <= p["date"] <= end.isoformat()]
    return {"label": label, "start": start.isoformat(), "end": end.isoformat(), "partial": end > ctx.d,
            "totals": {k: {kk: (round(vv) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in fams.items()},
            "activities": len(ws), "active_days": len({w["_date"] for w in ws}),
            "longest": {"workout_id": longest["source_id"], "distance_m": longest["distance_m"], "date": longest["_date"].isoformat(), "name": longest.get("name")} if longest else None,
            "fastest": fastest, "prs": sum(1 for f in fastest if f.get("pr")),
            "active_weeks": len(weeks), "total_weeks": total_weeks,
            "best_month": max(mrows, key=lambda r: r["load"]) if mrows else None,
            "quietest_month": min(mrows, key=lambda r: r["load"]) if len(mrows) > 1 else None, "months": mrows,
            "avg_sleep_min": round(mean(sl)) if sl else None, "avg_recovery": round(mean(rc)) if rc else None,
            "weight_change_kg": round(wp[-1]["v"] - wp[0]["v"], 1) if len(wp) >= 2 else None}


def recaps(ctx, sleep_hist, recovery_hist, weight_points, goals_progress):
    ys, ye = ctx.d.replace(month=1, day=1), ctx.d.replace(month=12, day=31)
    out = {"years": [], "months": []}
    first = ctx.first_day or ctx.d
    for y in range(first.year, ctx.d.year + 1):
        r = _recap(ctx, ys.replace(year=y), ye.replace(year=y), str(y), sleep_hist, recovery_hist, weight_points)
        if r:
            if y == ctx.d.year:
                r["goals"] = [{"title": g["title"], "status": g.get("status_label"), "progress_pct": g.get("progress_pct")} for g in goals_progress]
            out["years"].append(r)
    m = ctx.d.replace(day=1)
    for i in range(12):
        y, mo = m.year, m.month - i
        while mo <= 0:
            mo += 12
            y -= 1
        s = m.replace(year=y, month=mo)
        _, e = tu.period_bounds(s, "month")
        r = _recap(ctx, s, e, s.strftime("%B %Y"), sleep_hist, recovery_hist, weight_points)
        if r:
            out["months"].append(r)
    return out


# ----------------------------------------------------------------- weekly review
def weekly_review(ctx, snap):
    """Machine-readable weekly review for the agent (dist/weekly_review.json). Uses only computed keys."""
    ws = tu.week_start(ctx.d, ctx.week_start)
    last_ws = ws - timedelta(days=7)  # most recent completed week
    we = last_ws + timedelta(days=6)
    log = snap["training"]["log"]
    week_rows = [w for w in log["weeks"] if w["week"] == last_ws.isoformat()]
    day_loads = [r for r in snap["training"]["pmc"]["series"] if last_ws.isoformat() <= r["date"] <= we.isoformat()]
    sleep = [h for h in snap["sleep"]["history"] if last_ws.isoformat() <= h["date"] <= we.isoformat()]
    rec = [h for h in snap["recovery"]["history"] if last_ws.isoformat() <= h["date"] <= we.isoformat()]
    nut = [r for r in (snap["nutrition"].get("days") or []) if last_ws.isoformat() <= r["date"] <= we.isoformat()]
    pt = (snap["nutrition"].get("targets") or {}).get("protein_g")
    wt = [w for w in snap["body"]["weight"].get("weekly", []) if w["week"] == last_ws.isoformat()]
    return {
        "contract": "agame.weekly_review.v1", "week_start": last_ws.isoformat(), "week_end": we.isoformat(), "complete": we < ctx.d,
        "numbers": {
            "totals": week_rows[0]["totals"] if week_rows else None, "by_family": week_rows[0]["by_family"] if week_rows else None,
            "load_sum": round(sum(r["load"] for r in day_loads), 1) if day_loads else None,
            "load_days": len(day_loads),
            "sleep_avg_min": round(mean([h["asleep_min"] for h in sleep if h["asleep_min"]])) if sleep else None, "sleep_nights": len(sleep),
            "recovery_avg": round(mean([h["score"] for h in rec])) if rec else None,
            "protein_days_hit": sum(1 for r in nut if pt and (r.get("protein_g") or 0) >= pt) if (nut and pt) else None, "protein_days_logged": len(nut),
            "weight_median_kg": wt[0]["median"] if wt else None,
        },
        "four_week_log": log["weeks"][-5:-1] if len(log["weeks"]) >= 5 else log["weeks"],
        "pmc_end_of_week": next((r for r in reversed(day_loads)), None),
        "cardio_status": snap["training"]["status"],
        "goals": [{"id": g["id"], "title": g["title"], "status": g.get("status_label"), "progress_pct": g.get("progress_pct")} for g in snap["goals"]],
        "best_efforts_this_week": [e for e in snap.get("records_week", [])],
        "compliance_pct": snap["plans"]["last_week"]["header"].get("compliance_pct") if snap["plans"]["last_week"]["week"] == last_ws.isoformat() else snap["plans"]["this_week"]["header"].get("compliance_pct"),
        "next_week_intent": [{"date": s["date"], "type": s["type"], "title": s.get("title")} for s in snap["plans"]["next_week"]["sessions"] if s["type"] != "NPU"],
    }


# ----------------------------------------------------------------- data status
DOMAINS_STATUS = ("metrics", "sleep", "workouts", "body", "nutrition", "strength", "plans", "goals", "journal", "routes")


@metric("meta.data_status", method="freshness.v1", inputs=["current.json", "*.as_of"])
def data_status(ctx):
    cur = (ctx.data.get("current") or {}).get("domains") or {}
    out = {}
    for dom in DOMAINS_STATUS:
        p = ctx.data.get(dom) or {}
        c = cur.get(dom) or {}
        as_of = c.get("last_sample") or p.get("as_of")
        st = c.get("status") or p.get("status") or "missing"
        received = c.get("received")
        if p.get("status") == "missing" and p.get("fixture") != "empty":
            st, received = "missing", False  # file absent or emptied after the manifest was written
        age_h = None
        if as_of:
            try:
                age_h = round((ctx.now - tu.parse_ts(as_of)).total_seconds() / 3600, 1)
            except ValueError:
                age_h = None
        out[dom] = {"as_of": as_of, "last_sync": c.get("last_sync") or p.get("generated_at"), "status": st,
                    "received": received, "expected_for": c.get("expected_for"), "note": c.get("note"), "age_h": age_h,
                    "source": p.get("source")}
    sleep_missing = ((cur.get("sleep") or {}).get("expected_for") == ctx.d.isoformat() and (cur.get("sleep") or {}).get("received") is False) \
        or (out["sleep"]["status"] == "missing" and out["sleep"]["received"] is False)
    hk = ("metrics", "sleep", "workouts", "body", "nutrition")
    imports = (ctx.data.get("current") or {}).get("imports") or []
    morning = max([i["at"] for i in imports if i.get("at")] + [out[d]["last_sync"] for d in hk if out[d].get("last_sync")],
                  key=lambda ts: tu.parse_ts(ts), default=None)
    synced_today = bool(morning and tu.local_date(morning, ctx.tz) == ctx.d)
    overall = "ok" if synced_today and not sleep_missing else ("partial" if synced_today else ("stale" if morning else "missing"))
    return {"domains": out, "last_sync": morning, "synced_today": synced_today, "sleep_missing": sleep_missing, "overall": overall}
