"""Sleep metrics from HealthKit sleep stages. A night belongs to its wake date."""

from datetime import datetime, time, timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import linreg, clamp, mean, median, pearson, stdev
from agame.values import mv

ASLEEP = {"core", "deep", "rem", "asleep_unspecified"}


def _merge(intervals):
    iv = sorted(intervals)
    out = []
    for s, e in iv:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _minutes(intervals):
    return sum((e - s).total_seconds() for s, e in _merge(intervals)) / 60.0


def night_metrics(ctx, n):
    cfg = ctx.cfg["sleep"]
    segs = [(seg["stage"], tu.local_dt(seg["start"], ctx.tz), tu.local_dt(seg["end"], ctx.tz)) for seg in n["segments"]]
    by = {}
    for st, s, e in segs:
        by.setdefault(st, []).append((s, e))
    stage_min = {st: round(_minutes(iv), 1) for st, iv in by.items() if st != "in_bed"}
    asleep_iv = [iv for st in ASLEEP for iv in by.get(st, [])]
    asleep = _minutes(asleep_iv) if asleep_iv else None
    in_bed_iv = by.get("in_bed") or []
    if in_bed_iv:
        in_bed = _minutes(in_bed_iv)
        bed_start = min(s for s, _ in in_bed_iv)
    else:
        in_bed = (n["_end"] - n["_start"]).total_seconds() / 60.0
        bed_start = n["_start"]
    has_stages = any(st in by for st in ("core", "deep", "rem"))
    first_asleep = min((s for s, _ in asleep_iv), default=None)
    last_asleep = max((e for _, e in asleep_iv), default=None)
    latency = round((first_asleep - bed_start).total_seconds() / 60.0, 1) if (first_asleep and in_bed_iv) else None
    disruptions = []
    if first_asleep:
        for s, e in by.get("awake", []):
            if s >= first_asleep and e <= last_asleep and (e - s).total_seconds() / 60.0 >= cfg["disruption_min_awake_min"]:
                disruptions.append({"start": s.isoformat(), "end": e.isoformat(), "min": round((e - s).total_seconds() / 60.0, 1)})
    eff = (asleep / in_bed) if (asleep and in_bed) else None
    pct = {}
    if asleep and has_stages:
        for st in ("core", "deep", "rem"):
            pct[st] = round(100.0 * stage_min.get(st, 0) / asleep, 1)
    sleep_start = first_asleep or n["_start"]
    sleep_end = last_asleep or n["_end"]
    mid = sleep_start + (sleep_end - sleep_start) / 2
    anchor = datetime.combine(n["_date"], time(0, 0), tzinfo=ctx.tz)
    return {
        "id": n["source_id"], "date": n["_date"].isoformat(), "start": n["_start"].isoformat(), "end": n["_end"].isoformat(),
        "bed": bed_start.isoformat(), "wake": n["_end"].isoformat(),
        "asleep_min": round(asleep, 1) if asleep is not None else None, "in_bed_min": round(in_bed, 1),
        "efficiency": round(eff, 3) if eff is not None else None, "latency_min": latency,
        "stage_min": stage_min, "stage_pct": pct, "has_stages": has_stages,
        "disruptions": disruptions, "awake_min": stage_min.get("awake"),
        "midpoint_min": round((mid - anchor).total_seconds() / 60.0, 1),
        "source": n.get("source"), "is_nap": bool(n.get("is_nap")),
        "segments": [{"stage": st, "start": s.isoformat(), "end": e.isoformat()} for st, s, e in sorted(segs, key=lambda x: (x[1], x[0])) if st != "in_bed"],
    }


def _is_nap(ctx, n):
    if n.get("is_nap"):
        return True
    dur = (n["_end"] - n["_start"]).total_seconds() / 60.0
    return dur <= ctx.cfg["sleep"]["nap_max_min"] and 9 <= n["_start"].hour < 20


def nights_by_date(ctx):
    if hasattr(ctx, "_nights_by_date"):
        return ctx._nights_by_date
    main, naps = {}, {}
    for n in ctx.nights:
        if _is_nap(ctx, n):
            naps.setdefault(n["_date"], []).append(n)
            continue
        cur = main.get(n["_date"])
        if cur is None or (n["_end"] - n["_start"]) > (cur["_end"] - cur["_start"]):
            main[n["_date"]] = n
    metrics = {d: night_metrics(ctx, n) for d, n in main.items()}
    ctx._nights_by_date = (metrics, {d: [night_metrics(ctx, n) for n in ns] for d, ns in naps.items()})
    return ctx._nights_by_date


def base_need(ctx):
    m = ctx.phys_obj("sleep_need_base_min")
    if m and m.get("value"):
        return m["value"], "configured", m.get("kind", "configured")
    t = ctx.target("sleep_min")
    if t:
        return t, "target", "configured"
    if ctx.cfg["sleep"]["default_base_need_min"]:
        return ctx.cfg["sleep"]["default_base_need_min"], "default", "configured"
    nights, _ = nights_by_date(ctx)
    vals = [m["asleep_min"] for d, m in nights.items() if m["asleep_min"] and (ctx.d - d).days <= 30]
    if len(vals) >= 7:
        return median(vals), "observed_30_night_median", "estimated"
    return None, None, None


@metric("sleep.debt", unit="min", method="sleep_debt_decay.v1", inputs=["sleep.nights", "profile.sleep_need_base_min"])
def sleep_debt(ctx, d):
    cfg = ctx.cfg["sleep"]
    base, how, _ = base_need(ctx)
    if base is None:
        return None, 0
    nights, _ = nights_by_date(ctx)
    debt, seen = 0.0, 0
    for k in range(cfg["debt_days"]):
        nd = nights.get(d - timedelta(days=k))
        if nd and nd["asleep_min"] is not None:
            debt += max(0.0, base - nd["asleep_min"]) * (cfg["debt_decay"] ** k)
            seen += 1
    return (round(debt, 1) if seen else None), seen


@metric("sleep.need", unit="min", method="sleep_need.v1", inputs=["profile.sleep_need_base_min", "strain.day", "sleep.debt"])
def sleep_need(ctx, d, prev_strain_pct=None):
    cfg = ctx.cfg["sleep"]
    base, how, kind = base_need(ctx)
    if base is None:
        return mv(None, "min", note="Set a sleep need in profile (or log 7+ nights)", method="sleep_need.v1")
    add_strain = 0.0
    if prev_strain_pct is not None:
        add_strain = clamp((prev_strain_pct - 50) / 50.0, 0, 1) * cfg["strain_need_max_add_min"]
    debt, _ = sleep_debt(ctx, d - timedelta(days=1))
    add_debt = (debt or 0) * cfg["debt_repay_fraction"]
    return mv(round(base + add_strain + add_debt), "min", kind="estimated" if kind == "estimated" else "computed", method="sleep_need.v1",
              base=round(base), strain_add=round(add_strain), debt_add=round(add_debt), base_method=how)


@metric("sleep.regularity", unit="min", method="midpoint_sd_and_sri.v1", inputs=["sleep.nights"])
def regularity(ctx, d):
    nights, _ = nights_by_date(ctx)
    out = {}
    for win in (7, 14):
        mids = [nights[dd]["midpoint_min"] for dd in (d - timedelta(days=k) for k in range(win)) if dd in nights]
        out[f"midpoint_sd_{win}"] = round(stdev(mids), 1) if len(mids) >= max(3, win // 2) else None
        beds = [nights[dd]["bed"] for dd in (d - timedelta(days=k) for k in range(win)) if dd in nights]
        out[f"nights_{win}"] = len(mids)
    out["sri"] = sleep_regularity_index(ctx, d)
    return out


def sleep_regularity_index(ctx, d, days=7, bin_min=5):
    """SRI = -100 + 200 * P(same sleep/wake state 24 h apart), over the last `days` days."""
    cfg = ctx.cfg["sleep"]
    nights, _ = nights_by_date(ctx)
    have = [dd for dd in (d - timedelta(days=k) for k in range(days + 1)) if dd in nights]
    if len(have) < cfg["sri_min_nights"]:
        return None
    start = datetime.combine(d - timedelta(days=days), time(12, 0), tzinfo=ctx.tz)
    nbins = (days * 24 * 60) // bin_min
    state = [0] * nbins
    covered = [False] * nbins
    for dd in have:
        nm = nights[dd]
        for seg in nm["segments"]:
            s, e = tu.parse_ts(seg["start"]), tu.parse_ts(seg["end"])
            i0 = int((s - start).total_seconds() // (bin_min * 60))
            i1 = int((e - start).total_seconds() // (bin_min * 60))
            for i in range(max(0, i0), min(nbins, i1 + 1)):
                if seg["stage"] in ASLEEP:
                    state[i] = 1
        # the day window (noon to noon) around this wake date is observed
        w0 = int((datetime.combine(dd - timedelta(days=1), time(12, 0), tzinfo=ctx.tz) - start).total_seconds() // (bin_min * 60))
        for i in range(max(0, w0), min(nbins, w0 + (24 * 60) // bin_min)):
            covered[i] = True
    lag = (24 * 60) // bin_min
    same = total = 0
    for i in range(nbins - lag):
        if covered[i] and covered[i + lag]:
            total += 1
            same += 1 if state[i] == state[i + lag] else 0
    if total < lag:
        return None
    return round(-100 + 200.0 * same / total, 1)


@metric("sleep.score", unit="%", method="sleep_score.v1", inputs=["sleep.need", "sleep.efficiency", "sleep.regularity", "sleep.stages"])
def sleep_score(ctx, nm, need_v, reg):
    cfg = ctx.cfg["sleep"]
    w = cfg["weights"]
    comps = {}
    if nm["asleep_min"] is not None and need_v:
        comps["duration"] = clamp(nm["asleep_min"] / need_v, 0, 1) * 100
    if nm["efficiency"] is not None and nm["has_stages"]:
        lo, hi = cfg["efficiency_range"]
        comps["efficiency"] = clamp((nm["efficiency"] - lo) / (hi - lo), 0, 1) * 100
    sd = reg.get("midpoint_sd_7")
    if sd is not None:
        comps["consistency"] = clamp(1 - sd / cfg["consistency_sd_max_min"], 0, 1) * 100
    if nm["has_stages"] and nm["stage_pct"]:
        parts = []
        for st, (lo, hi) in cfg["stage_targets_pct"].items():
            v = nm["stage_pct"].get(st, 0)
            parts.append(100.0 if lo <= v <= hi else clamp(100 - 8 * (lo - v if v < lo else v - hi), 0, 100))
        comps["stages"] = sum(parts) / len(parts)
    if "duration" not in comps:
        return mv(None, "%", note="Need sleep duration and a sleep need", method="sleep_score.v1"), comps
    tw = sum(w[k] for k in comps)
    score = sum(comps[k] * w[k] for k in comps) / tw
    status = "ok" if len(comps) == 4 else "partial"
    return mv(round(score), "%", method="sleep_score.v1", status=status, as_of=nm["end"], source=nm.get("source"),
              components={k: round(v) for k, v in comps.items()},
              missing_components=[k for k in w if k not in comps]), comps


def summary(ctx, strain_by_day=None):
    """Full sleep block for computed.json."""
    nights, naps = nights_by_date(ctx)
    strain_by_day = strain_by_day or {}
    history = []
    dates = sorted(d for d in nights if (ctx.d - d).days <= 365)
    for d in dates:
        nm = nights[d]
        need = sleep_need(ctx, d, strain_by_day.get(d - timedelta(days=1)))
        reg = regularity(ctx, d)
        sc, _ = sleep_score(ctx, nm, need["v"], reg)
        debt, _ = sleep_debt(ctx, d)
        history.append({"date": d.isoformat(), "asleep_min": nm["asleep_min"], "in_bed_min": nm["in_bed_min"], "need_min": need["v"],
                        "score": sc["v"], "efficiency": nm["efficiency"], "debt_min": debt, "bed": nm["bed"], "wake": nm["wake"],
                        "midpoint_min": nm["midpoint_min"], "stage_pct": nm["stage_pct"], "stage_min": nm["stage_min"],
                        "disruptions": len(nm["disruptions"]), "latency_min": nm["latency_min"]})
    last_date = dates[-1] if dates else None
    out = {"history": history, "naps": [], "status": "missing"}
    if last_date is None:
        out["last_night"] = None
        out["score"] = mv(None, "%", note="No sleep data yet", method="sleep_score.v1")
        return out
    nm = nights[last_date]
    need = sleep_need(ctx, last_date, strain_by_day.get(last_date - timedelta(days=1)))
    reg = regularity(ctx, last_date)
    sc, comps = sleep_score(ctx, nm, need["v"], reg)
    debt, seen = sleep_debt(ctx, last_date)
    stale = last_date < ctx.d
    if stale:
        sc = dict(sc)
        sc["status"] = "stale"
    out.update({
        "last_night": nm, "last_date": last_date.isoformat(), "stale": stale,
        "score": sc, "need": dict(need, as_of=nm["end"]) if need["v"] is not None else need,
        "debt": mv(debt, "min", method="sleep_debt_decay.v1", nights=seen, status="stale" if stale else None, as_of=nm["end"] if debt is not None else None),
        "regularity": reg, "status": "stale" if stale else sc["status"],
        "naps": [n for d in sorted(naps) if (ctx.d - d).days <= 14 for n in naps[d]],
        "base_need": base_need(ctx)[0],
    })
    # 14/30/90-day averages
    for win in (7, 30, 90):
        rows = [h for h in history if (ctx.d - tu.parse_date(h["date"])).days < win]
        a = mean([r["asleep_min"] for r in rows])
        s = mean([r["score"] for r in rows])
        out[f"avg_{win}"] = {"asleep_min": round(a) if a is not None else None,
                             "score": round(s) if s is not None else None,
                             "efficiency": mean([r["efficiency"] for r in rows]), "nights": len(rows)}
    return out


@metric("sleep.recovery_correlation", method="pearson_gated.v1", inputs=["sleep.asleep_min", "recovery.score"])
def recovery_correlation(ctx, history, recovery_by_day):
    cfg = ctx.cfg["sleep"]
    xs, ys = [], []
    for h in history:
        d = tu.parse_date(h["date"])
        r = recovery_by_day.get(d)
        if h["asleep_min"] is not None and r is not None:
            xs.append(h["asleep_min"])
            ys.append(r)
    r, n = pearson(xs, ys)
    need = cfg["correlation_min_nights"]
    points = [{"x": x, "y": y} for x, y in list(zip(xs, ys))[-120:]]
    if n < need or r is None:
        return {"status": "insufficient", "n": n, "needed": need, "points": points}
    if abs(r) < ctx.cfg["insights"]["correlation_min_abs_r"]:
        return {"status": "no_clear_effect", "r": round(r, 2), "n": n, "needed": need, "points": points}
    slope, icpt = linreg(xs, ys)
    lo, hi = min(xs), max(xs)
    return {"status": "ok", "r": round(r, 2), "n": n, "direction": "positive" if r > 0 else "negative",
            "strength": "strong" if abs(r) >= 0.5 else ("moderate" if abs(r) >= 0.3 else "weak"), "points": points,
            "fit": [{"x": lo, "y": round(icpt + slope * lo, 1)}, {"x": hi, "y": round(icpt + slope * hi, 1)}] if slope is not None else None}
