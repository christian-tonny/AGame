"""Zones, session load (Banister TRIMP), Fitness/Fatigue/Form, Cardio Status, weekly effort.

Definitions (README.md §6):
- HR zones from HR max (5-zone) or LTHR (7-zone); never from an age formula.
- Session load = Banister TRIMP from the HR stream. Avg-HR TRIMP when only averages exist
  (estimated). Session-RPE x minutes x k when no HR at all (estimated). Else missing.
- CTL = 42-day EWMA, ATL = 7-day EWMA (k = 1/N). TSB(d) = CTL(d-1) - ATL(d-1).
"""

import math
from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import clamp, linreg, mean, median
from agame.values import mv


# ----------------------------------------------------------------- resting HR / zones
def resting_hr(ctx, d=None):
    """Resting HR used for HR reserve: configured value, else 14-day median of daily RHR."""
    d = d or ctx.d
    conf = ctx.phys_obj("hr_rest")
    if conf and conf.get("value"):
        return conf["value"], "configured"
    daily = ctx.daily("resting_hr_bpm")
    vals = [v for dd, v in daily.items() if d - timedelta(days=14) < dd <= d]
    if not vals:
        vals = [v for dd, v in daily.items() if dd <= d][-14:]
    m = median(vals)
    return (m, "observed_14d_median") if m is not None else (None, None)


@metric("zones.hr", unit="bpm", method="zones.hr.v1", inputs=["profile.physiology.hr_max", "profile.physiology.lthr"])
def hr_zones(ctx):
    z = ctx.profile.get("zones") or {}
    model = z.get("model") or "5zone"
    custom = z.get("hr_custom_bpm")
    hrmax_o, lthr_o = ctx.phys_obj("hr_max"), ctx.phys_obj("lthr")
    if custom:
        zones = [{"name": f"Z{i + 1}", "low": lo, "high": hi} for i, (lo, hi) in enumerate(custom)]
        return {"zones": zones, "model": "custom", "basis": "custom", "method": "configured custom bounds",
                "date": None, "status": "ok", "kind": "configured"}
    if model == "7zone":
        if not lthr_o:
            return {"zones": None, "model": model, "status": "missing", "reason": "LTHR not configured (7-zone model uses LTHR)"}
        lthr = lthr_o["value"]
        pct = ctx.cfg["zones"]["hr_7zone_pct_lthr"]
        zones = [{"name": f"Z{i + 1}", "low": round(lo * lthr), "high": round(hi * lthr)} for i, (lo, hi) in enumerate(pct)]
        return {"zones": zones, "model": model, "basis": "lthr", "basis_value": lthr, "method": lthr_o.get("method"),
                "date": lthr_o.get("date"), "status": "ok", "kind": lthr_o.get("kind", "configured")}
    if not hrmax_o:
        return {"zones": None, "model": model, "status": "missing", "reason": "HR max not configured"}
    hrmax = hrmax_o["value"]
    pct = ctx.cfg["zones"]["hr_5zone_pct_hrmax"]
    zones = [{"name": f"Z{i + 1}", "low": round(lo * hrmax), "high": round(hi * hrmax)} for i, (lo, hi) in enumerate(pct)]
    zones[0]["low"] = 0
    return {"zones": zones, "model": model, "basis": "hr_max", "basis_value": hrmax, "method": hrmax_o.get("method"),
            "date": hrmax_o.get("date"), "status": "ok", "kind": hrmax_o.get("kind", "configured")}


def effective_threshold_pace(ctx):
    """Configured threshold pace, or the newest accepted calibration candidate."""
    conf = ctx.phys_obj("threshold_pace_s_per_km")
    if ctx.profile.get("auto_accept_thresholds"):
        cands = [c for c in threshold_candidates(ctx) if c["metric"] == "threshold_pace_s_per_km"]
        if cands and (not conf or (cands[-1]["date"] or "") > (conf.get("date") or "")):
            c = cands[-1]
            return {"value": c["value"], "method": c["method"], "date": c["date"], "kind": "observed"}
    return conf


@metric("zones.pace", unit="s/km", method="zones.pace.v1", inputs=["profile.physiology.threshold_pace_s_per_km"])
def pace_zones(ctx):
    z = ctx.profile.get("zones") or {}
    custom = z.get("pace_custom_s_per_km")
    if custom:
        zones = [{"name": f"Z{i + 1}", "slow": lo, "fast": hi} for i, (lo, hi) in enumerate(custom)]
        return {"zones": zones, "basis": "custom", "status": "ok", "kind": "configured"}
    thr = effective_threshold_pace(ctx)
    if not thr:
        return {"zones": None, "status": "missing", "reason": "Threshold pace not configured"}
    model = z.get("model") or "5zone"
    pct = ctx.cfg["zones"]["pace_7zone_pct_threshold_speed" if model == "7zone" else "pace_5zone_pct_threshold_speed"]
    tspeed = 1000.0 / thr["value"]
    zones = []
    for i, (lo, hi) in enumerate(pct):
        slow = None if lo <= 0 else round(1000.0 / (tspeed * lo))
        fast = round(1000.0 / (tspeed * hi))
        zones.append({"name": f"Z{i + 1}", "slow": slow, "fast": fast})
    return {"zones": zones, "basis": "threshold_pace", "basis_value": thr["value"], "method": thr.get("method"),
            "date": thr.get("date"), "status": "ok", "kind": thr.get("kind", "configured")}


# ----------------------------------------------------------------- streams
def hr_stream(w):
    s = w.get("samples") or {}
    t, hr = s.get("t"), s.get("hr")
    if not t or not hr:
        return None
    pts = [(ti, h) for ti, h in zip(t, hr) if ti is not None and h is not None]
    return pts if len(pts) >= 2 else None


def _intervals(pts, cap=None):
    """Yield (dt_seconds, value) for each step, capping long gaps."""
    if not pts:
        return
    dts = [pts[i][0] - pts[i - 1][0] for i in range(1, len(pts))]
    med = median([d for d in dts if d > 0]) or 1
    cap = cap or max(5.0, 3 * med)
    for i in range(1, len(pts)):
        dt = min(cap, max(0.0, pts[i][0] - pts[i - 1][0]))
        yield dt, (pts[i - 1][1] + pts[i][1]) / 2.0


def time_in_zones(pts, zones):
    out = [0.0] * len(zones)
    for dt, v in _intervals(pts):
        idx = 0
        for i, z in enumerate(zones):
            if v >= z["low"]:
                idx = i
        out[idx] += dt
    return out


def trimp_from_stream(pts, hrmax, hrrest, k):
    a, b = k
    total = 0.0
    for dt, hr in _intervals(pts):
        hrr = clamp((hr - hrrest) / (hrmax - hrrest), 0.0, 1.0)
        total += (dt / 60.0) * hrr * a * math.exp(b * hrr)
    return total


def trimp_from_avg(avg_hr, minutes, hrmax, hrrest, k):
    a, b = k
    hrr = clamp((avg_hr - hrrest) / (hrmax - hrrest), 0.0, 1.0)
    return minutes * hrr * a * math.exp(b * hrr)


def _trimp_k(ctx):
    sex = (ctx.profile.get("athlete") or {}).get("sex")
    ks = ctx.cfg["load"]["trimp_k"]
    return ks.get(sex) or ks["default"], ("sex-specific" if sex in ks else "generic")


def _hr_basis(ctx, d):
    hrmax = ctx.phys("hr_max")
    hrrest, _ = resting_hr(ctx, d)
    return hrmax, hrrest


def _raw_hr_load(ctx, w):
    hrmax, hrrest = _hr_basis(ctx, w["_date"])
    if not hrmax or not hrrest:
        return None, None
    k, _ = _trimp_k(ctx)
    pts = hr_stream(w)
    if pts:
        return trimp_from_stream(pts, hrmax, hrrest, k), "trimp_stream"
    if w.get("avg_hr"):
        return trimp_from_avg(w["avg_hr"], w["_dur"] / 60.0, hrmax, hrrest, k), "trimp_avg_hr"
    return None, None


def srpe_factor(ctx):
    """k converting session-RPE (RPE x min) to TRIMP units; personal when enough paired sessions."""
    if hasattr(ctx, "_srpe_k"):
        return ctx._srpe_k
    pairs = []
    for w in ctx.workouts:
        a = w.get("_ann")
        if a and a.get("rpe"):
            v, method = _raw_hr_load(ctx, w)
            if v and method == "trimp_stream":
                pairs.append((a["rpe"] * w["_dur"] / 60.0, v))
    cfg = ctx.cfg["load"]
    if len(pairs) >= cfg["srpe_calibration_min_pairs"]:
        k = sum(p[1] for p in pairs) / sum(p[0] for p in pairs)
        res = (k, "personal", len(pairs))
    else:
        res = (cfg["srpe_to_trimp_default"], "default", len(pairs))
    ctx._srpe_k = res
    return res


@metric("load.session", unit="TRIMP", method="banister_trimp.v1", inputs=["workout.samples.hr", "profile.hr_max", "metrics.resting_hr_bpm", "load.rpe"])
def session_load(ctx, w):
    cache = getattr(ctx, "_load_cache", None)
    if cache is None:
        cache = ctx._load_cache = {}
    if w["source_id"] in cache:
        return cache[w["source_id"]]
    v, method = _raw_hr_load(ctx, w)
    if v is not None:
        res = mv(round(v, 1), "TRIMP", kind="computed" if method == "trimp_stream" else "estimated", method=method,
                 as_of=w["end"], source=w.get("source"))
    else:
        a = w.get("_ann")
        if a and a.get("rpe"):
            k, how, n = srpe_factor(ctx)
            res = mv(round(a["rpe"] * w["_dur"] / 60.0 * k, 1), "TRIMP", kind="estimated", method="session_rpe",
                     as_of=w["end"], note=f"RPE {a['rpe']} × {round(w['_dur'] / 60)} min × {k:.2f} ({how} factor)")
        else:
            reason = "HR max not configured" if not ctx.phys("hr_max") else ("No resting HR" if not resting_hr(ctx, w["_date"])[0] else "No heart rate or RPE")
            res = mv(None, "TRIMP", method="none", note=reason)
    cache[w["source_id"]] = res
    return res


def workout_zones(ctx, w):
    hz = hr_zones(ctx)
    pts = hr_stream(w)
    if not hz.get("zones") or not pts:
        return None
    secs = time_in_zones(pts, hz["zones"])
    return [{"name": z["name"], "low": z["low"], "high": z["high"], "s": round(s)} for z, s in zip(hz["zones"], secs)]


# ----------------------------------------------------------------- daily load + PMC
def daily_loads(ctx):
    """dict date -> {'load': float, 'known': bool, 'estimated': bool, 'missing_sessions': int}."""
    if hasattr(ctx, "_daily_loads"):
        return ctx._daily_loads
    out = {}
    if ctx.first_day is None:
        ctx._daily_loads = out
        return out
    for d in tu.daterange(ctx.first_day, ctx.d):
        ws = ctx.workouts_by_day.get(d, [])
        total, est, miss = 0.0, False, 0
        for w in ws:
            sl = session_load(ctx, w)
            if sl["v"] is None:
                miss += 1
            else:
                total += sl["v"]
                est = est or sl["kind"] == "estimated"
        out[d] = {"load": total, "known": d in ctx.covered, "estimated": est, "missing_sessions": miss}
    ctx._daily_loads = out
    return out


@metric("load.pmc", unit="TRIMP/day", method="pmc_ewma.v1", inputs=["load.session"])
def pmc(ctx):
    cfg = ctx.cfg["load"]
    dl = daily_loads(ctx)
    if not dl:
        return {"series": [], "status": "missing", "reason": "No training or daily data yet"}
    kc, ka = 1.0 / cfg["ctl_days"], 1.0 / cfg["atl_days"]
    ctl = atl = 0.0
    series = []
    days_known = 0
    for d in sorted(dl):
        rec = dl[d]
        tsb = ctl - atl
        load = rec["load"]
        ctl = ctl + (load - ctl) * kc
        atl = atl + (load - atl) * ka
        days_known += 1 if rec["known"] else 0
        series.append({"date": d.isoformat(), "load": round(load, 1), "ctl": round(ctl, 2), "atl": round(atl, 2),
                       "tsb": round(tsb, 2), "known": rec["known"], "estimated": rec["estimated"]})
    span = (ctx.d - ctx.first_day).days + 1
    unknown_recent = sum(1 for r in series[-42:] if not r["known"])
    status = "calibrating" if span < cfg["ctl_days"] else ("partial" if unknown_recent > 7 else "ok")
    return {"series": series, "status": status, "days": span, "unknown_days_42": unknown_recent,
            "calibrated_from": (ctx.first_day + timedelta(days=cfg["ctl_days"])).isoformat()}


def pmc_today(ctx, p=None):
    p = p or pmc(ctx)
    if not p["series"]:
        return None
    return p["series"][-1]


@metric("load.cardio_status", method="cardio_status.v1", inputs=["load.pmc"])
def cardio_status(ctx, p=None):
    p = p or pmc(ctx)
    st = ctx.cfg["load"]["status"]
    if not p["series"]:
        return mv(None, note="No training data", method="cardio_status.v1")
    today = p["series"][-1]
    wk = p["series"][-8] if len(p["series"]) >= 8 else p["series"][0]
    ramp = today["ctl"] - wk["ctl"]
    tsb = today["tsb"]
    if p["status"] == "calibrating":
        label = "calibrating"
    elif tsb < st["overreaching_tsb"]:
        label = "overreaching"
    elif tsb < st["fatigued_tsb"]:
        label = "fatigued"
    elif ramp >= st["productive_ramp_per_week"]:
        label = "productive"
    elif ramp <= st["detraining_ramp_per_week"]:
        label = "detraining"
    else:
        label = "maintaining"
    return mv(label, kind="computed", method="cardio_status.v1", as_of=ctx.local_iso(ctx.now), status="calibrating" if label == "calibrating" else "ok",
              ramp=round(ramp, 1), tsb=round(tsb, 1), ctl=round(today["ctl"], 1), atl=round(today["atl"], 1),
              ramp_warning=ramp >= st["ramp_warning_per_week"])


def _sport_trimp_per_min(ctx, sport_family, days=60):
    vals = []
    for w in ctx.workouts:
        if w["_family"] == sport_family and (ctx.d - w["_date"]).days <= days:
            sl = session_load(ctx, w)
            if sl["v"] is not None and w["_dur"] > 0:
                vals.append(sl["v"] / (w["_dur"] / 60.0))
    return median(vals)


def planned_load(ctx, s):
    if s.get("load_planned") is not None:
        return s["load_planned"], "planned"
    if not s.get("duration_s"):
        return 0.0, "rest"
    from agame.compute.ctx import sport_family
    fam = sport_family(s.get("sport") or "other")
    tpm = _sport_trimp_per_min(ctx, fam)
    if tpm is None:
        return None, "unknown"
    factor = 1.25 if s.get("type") in ctx.cfg["plans"]["hard_types"] else 1.0
    return tpm * s["duration_s"] / 60.0 * factor, "estimated_from_history"


@metric("load.forecast", unit="TRIMP/day", method="pmc_projection.v1", inputs=["load.pmc", "plans.sessions"])
def forecast(ctx, p=None, sessions=None):
    p = p or pmc(ctx)
    if not p["series"]:
        return {"series": [], "status": "missing"}
    cfg = ctx.cfg["load"]
    kc, ka = 1.0 / cfg["ctl_days"], 1.0 / cfg["atl_days"]
    last = p["series"][-1]
    ctl, atl = last["ctl"], last["atl"]
    by_day = defaultdict(list)
    for s in sessions if sessions is not None else (ctx.data.get("plans") or {}).get("sessions", []):
        by_day[s["date"]].append(s)
    out, unknown = [], 0
    for i in range(1, cfg["forecast_days"] + 1):
        d = ctx.d + timedelta(days=i)
        load = 0.0
        for s in by_day.get(d.isoformat(), []):
            pl, how = planned_load(ctx, s)
            if pl is None:
                unknown += 1
            else:
                load += pl
        tsb = ctl - atl
        ctl += (load - ctl) * kc
        atl += (load - atl) * ka
        out.append({"date": d.isoformat(), "load": round(load, 1), "ctl": round(ctl, 2), "atl": round(atl, 2), "tsb": round(tsb, 2)})
    return {"series": out, "status": "partial" if unknown else "ok", "kind": "estimated", "label": "projection", "unknown_sessions": unknown}


# ----------------------------------------------------------------- weekly effort
@metric("load.weekly_effort", unit="TRIMP/week", method="weekly_effort_band.v1", inputs=["load.session"])
def weekly_effort(ctx):
    cfg = ctx.cfg["load"]
    dl = daily_loads(ctx)
    weeks = defaultdict(float)
    known = defaultdict(int)
    for d, rec in dl.items():
        ws = tu.week_start(d, ctx.week_start)
        weeks[ws] += rec["load"]
        known[ws] += 1 if rec["known"] else 0
    cur_ws = tu.week_start(ctx.d, ctx.week_start)
    rows = []
    for i in range(cfg["re_band_weeks"] + 4, -1, -1):
        ws = cur_ws - timedelta(days=7 * i)
        rows.append({"week": ws.isoformat(), "load": round(weeks.get(ws, 0.0), 1) if ws in weeks else None,
                     "partial": ws == cur_ws, "known_days": known.get(ws, 0)})
    prior = [r for r in rows if not r["partial"] and r["load"] is not None][-cfg["re_band_weeks"]:]
    if len(prior) < 3:
        return {"weeks": rows, "band": None, "hint": None, "status": "calibrating"}
    n = len(prior)
    weights = [(i + 1) for i in range(n)]  # recency weighted
    wavg = sum(w * r["load"] for w, r in zip(weights, prior)) / sum(weights)
    lo, hi = wavg * (1 - cfg["re_band_pct"]), wavg * (1 + cfg["re_band_pct"])
    last_full = prior[-1]["load"]
    cur = rows[-1]["load"] or 0.0
    elapsed = (ctx.d - cur_ws).days + 1
    projected = cur / elapsed * 7 if elapsed else None
    if last_full > hi:
        hint = "recover"
    elif last_full < lo:
        hint = "increase"
    else:
        hint = "maintain"
    return {"weeks": rows, "band": {"low": round(lo, 1), "high": round(hi, 1), "weighted_avg": round(wavg, 1), "weeks": n},
            "hint": hint, "current": round(cur, 1), "projected": round(projected, 1) if projected is not None else None,
            "status": "ok"}


@metric("load.zone_distribution", unit="s", method="zone_distribution.v1", inputs=["zones.hr", "workout.samples.hr"])
def zone_distribution(ctx, weeks=12):
    hz = hr_zones(ctx)
    if not hz.get("zones"):
        return {"status": "missing", "reason": hz.get("reason"), "weeks": []}
    cur_ws = tu.week_start(ctx.d, ctx.week_start)
    out = []
    for i in range(weeks - 1, -1, -1):
        ws = cur_ws - timedelta(days=7 * i)
        secs = [0.0] * len(hz["zones"])
        for d in tu.daterange(ws, ws + timedelta(days=6)):
            for w in ctx.workouts_by_day.get(d, []):
                pts = hr_stream(w)
                if pts:
                    for j, s in enumerate(time_in_zones(pts, hz["zones"])):
                        secs[j] += s
        out.append({"week": ws.isoformat(), "s": [round(s) for s in secs], "partial": ws == cur_ws})
    return {"status": "ok", "zones": [z["name"] for z in hz["zones"]], "weeks": out}


# ----------------------------------------------------------------- threshold calibration
@metric("zones.threshold_candidates", method="threshold_calibration.v1", inputs=["workouts.tags", "workouts.samples"])
def threshold_candidates(ctx):
    if hasattr(ctx, "_thr_cands"):
        return ctx._thr_cands
    from agame.compute.activity import best_effort_time
    tcfg = ctx.cfg["zones"]["threshold_candidates"]
    out = []
    for w in ctx.workouts:
        tags = set(w.get("tags") or [])
        a = w.get("_ann") or {}
        if a.get("race"):
            tags.add("race")
        if not tags & set(tcfg["test_tags"]):
            continue
        s = w.get("samples") or {}
        if "test_5k" in tags or "race" in tags:
            D = 5000.0 if "test_5k" in tags else (w.get("distance_m") or 0)
            T = best_effort_time(s.get("t"), s.get("dist_m"), D) if D else None
            if T is None and "race" in tags and w.get("distance_m"):
                T, D = w["_dur"], w["distance_m"]
            if T:
                d60 = D * (3600.0 / T) ** (1.0 / tcfg["riegel_exponent"])
                out.append({"metric": "threshold_pace_s_per_km", "value": round(3600.0 / d60 * 1000.0),
                            "method": f"{'5K test' if 'test_5k' in tags else 'race'}: 60-min equivalent pace (Riegel)",
                            "date": w["_date"].isoformat(), "workout_id": w["source_id"], "source_effort_s": round(T), "source_effort_m": D})
        if "test_30min" in tags:
            pts = hr_stream(w)
            if pts:
                end = pts[-1][0]
                last20 = [h for t, h in pts if t >= end - 1200]
                if last20:
                    out.append({"metric": "lthr", "value": round(mean(last20) * tcfg["lthr_from_30min_last20_factor"]),
                                "method": "30-min test: avg HR of last 20 min", "date": w["_date"].isoformat(), "workout_id": w["source_id"]})
    out.sort(key=lambda c: (c["date"], c["metric"]))
    for c in out:
        conf = ctx.phys_obj(c["metric"])
        c["current"] = conf.get("value") if conf else None
        c["delta"] = (c["value"] - c["current"]) if c["current"] is not None else None
        c["applied"] = bool(ctx.profile.get("auto_accept_thresholds"))
    ctx._thr_cands = out
    return out
