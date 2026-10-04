"""Recovery / readiness: configurable composite of HRV delta, resting-HR delta and sleep debt.

Each component is z-scored against the athlete's own rolling baseline (default 60 days,
excluding the day itself) and mapped to 0-100 (50 = baseline). Missing components are
excluded and the remaining weights re-normalised; they are listed as missing.
"""

import math
from datetime import timedelta

from agame.compute import metric
from agame.compute.ctx import clamp, mean, percentile, stdev
from agame.compute import sleep as sleepm
from agame.values import mv


def daily_hrv(ctx):
    """dict date -> HRV (ms): overnight samples within that date's main sleep, else morning, else day mean."""
    if hasattr(ctx, "_daily_hrv"):
        return ctx._daily_hrv
    nights, _ = sleepm.nights_by_date(ctx)
    by_day = {}
    for dt, dd, v, _ in ctx.series("hrv_sdnn_ms"):
        by_day.setdefault(dd, []).append((dt, v))
    out = {}
    for dd, pts in by_day.items():
        nm = nights.get(dd)
        chosen = []
        if nm:
            s, e = nm["start"], nm["end"]
            chosen = [v for dt, v in pts if dt is not None and s <= dt.isoformat() <= e]
        if not chosen:
            chosen = [v for dt, v in pts if dt is not None and dt.hour < 12]
        if not chosen:
            chosen = [v for _, v in pts]
        out[dd] = sum(chosen) / len(chosen)
    ctx._daily_hrv = out
    return out


def _baseline(daily, d, days, transform=None):
    vals = [daily[dd] for dd in daily if d - timedelta(days=days) <= dd < d]
    if transform:
        vals = [transform(v) for v in vals]
    return vals


def _z_component(today, base_vals, invert, cfg):
    if today is None or len(base_vals) < cfg["min_baseline_days"]:
        return None
    m, sd = mean(base_vals), stdev(base_vals)
    if not sd:
        sd = abs(m) * 0.05 or 1.0
    z = (today - m) / sd
    if invert:
        z = -z
    return {"z": round(z, 2), "score": round(clamp(50 + cfg["z_scale"] * z, 0, 100), 1), "baseline_n": len(base_vals)}


@metric("recovery.score", unit="%", method="recovery_composite.v1",
        inputs=["metrics.hrv_sdnn_ms", "metrics.resting_hr_bpm", "sleep.debt", "metrics.respiratory_rate_brpm"])
def recovery_for(ctx, d, strain_by_day=None):
    cfg = ctx.cfg["recovery"]
    w = cfg["weights"]
    hrv = daily_hrv(ctx)
    rhr = ctx.daily("resting_hr_bpm")
    rr = ctx.daily("respiratory_rate_brpm")
    comps, missing = {}, []
    as_ofs = []

    # HRV (log-transformed)
    if w.get("hrv"):
        t = hrv.get(d)
        c = _z_component(math.log(t) if t else None, _baseline(hrv, d, cfg["baseline_days"], math.log), False, cfg)
        if c:
            base = math.exp(mean(_baseline(hrv, d, cfg["baseline_days"], math.log)))
            c.update({"value": round(t, 1), "baseline": round(base, 1), "unit": "ms", "delta_pct": round(100 * (t / base - 1), 1), "label": "HRV"})
            comps["hrv"] = c
        else:
            missing.append({"id": "hrv", "reason": "No HRV this morning" if t is None else "Building HRV baseline"})
    if w.get("rhr"):
        t = rhr.get(d)
        c = _z_component(t, _baseline(rhr, d, cfg["baseline_days"]), True, cfg)
        if c:
            base = mean(_baseline(rhr, d, cfg["baseline_days"]))
            c.update({"value": round(t, 1), "baseline": round(base, 1), "unit": "bpm", "delta": round(t - base, 1), "label": "Resting HR"})
            comps["rhr"] = c
        else:
            missing.append({"id": "rhr", "reason": "No resting HR this morning" if t is None else "Building resting HR baseline"})
    if w.get("sleep_debt"):
        nights, _ = sleepm.nights_by_date(ctx)
        debt, seen = sleepm.sleep_debt(ctx, d)
        if debt is not None and d in nights:
            comps["sleep_debt"] = {"value": round(debt), "unit": "min", "label": "Sleep debt",
                                   "score": round(100 * (1 - clamp(debt / cfg["max_sleep_debt_min"], 0, 1)), 1)}
        else:
            missing.append({"id": "sleep_debt", "reason": "Last night's sleep not synced" if d not in nights else "Sleep need not set"})
    if w.get("resp_rate"):
        t = rr.get(d)
        c = _z_component(t, _baseline(rr, d, cfg["baseline_days"]), False, cfg)
        if c:
            c["score"] = round(100 - clamp(abs(c["z"]) * 30, 0, 100), 1)
            c.update({"value": round(t, 1), "unit": "br/min", "label": "Respiratory rate"})
            comps["resp_rate"] = c
        else:
            missing.append({"id": "resp_rate", "reason": "No respiratory rate"})
    if w.get("prior_strain") and strain_by_day:
        sp = strain_by_day.get(d - timedelta(days=1))
        if sp is not None:
            comps["prior_strain"] = {"value": round(sp), "unit": "%", "label": "Yesterday's strain", "score": round(100 - sp, 1)}

    if "hrv" not in comps and "rhr" not in comps:
        return None
    tw = sum(w[k] for k in comps)
    score = sum(comps[k]["score"] * w[k] for k in comps) / tw
    for k, c in comps.items():
        c["weight"] = round(w[k] / tw, 3)
        c["contribution"] = round((c["score"] - 50) * w[k] / tw, 1)
    nb = min((c.get("baseline_n", 99) for c in comps.values()), default=0)
    have_both = "hrv" in comps and "rhr" in comps
    confidence = "high" if (have_both and nb >= cfg["high_confidence_days"] and not missing) else ("medium" if nb >= cfg["min_baseline_days"] and have_both else "low")
    expected = [k for k, v in w.items() if v and (k != "prior_strain" or strain_by_day)]
    return {"date": d.isoformat(), "score": round(score), "components": comps, "missing": missing, "confidence": confidence,
            "coverage": round(len(comps) / max(1, len(expected)), 2)}


def summary(ctx, strain_by_day=None):
    cfg = ctx.cfg["recovery"]
    hist = []
    start = ctx.d - timedelta(days=365)
    days = sorted(set(daily_hrv(ctx)) | set(ctx.daily("resting_hr_bpm")))
    by_day = {}
    for d in days:
        if d < start or d > ctx.d:
            continue
        r = recovery_for(ctx, d, strain_by_day)
        if r:
            by_day[d] = r
            hist.append({"date": r["date"], "score": r["score"], "confidence": r["confidence"],
                         "hrv": r["components"].get("hrv", {}).get("value"), "rhr": r["components"].get("rhr", {}).get("value")})
    today = by_day.get(ctx.d)
    stale = False
    if today is None and by_day:
        today = by_day[max(by_day)]
        stale = True
    scores60 = [h["score"] for h in hist if (ctx.d - _date(h["date"])).days <= 60]
    nr = None
    if len(scores60) >= cfg["normal_range_min_days"]:
        lo, hi = cfg["normal_range_pct"]
        nr = {"low": round(percentile(scores60, lo)), "high": round(percentile(scores60, hi))}
    if today is None:
        reason = "Need HRV or resting HR with a baseline of %d days" % cfg["min_baseline_days"]
        return {"score": mv(None, "%", note=reason, method="recovery_composite.v1"), "history": hist, "normal_range": nr, "by_day": {}}
    as_of = None
    for sid in ("hrv_sdnn_ms", "resting_hr_bpm"):
        a = ctx.series_as_of(sid)
        as_of = max(as_of, a) if (as_of and a) else (as_of or a)
    band = "low" if today["score"] < cfg["bands"]["low"] else ("high" if today["score"] >= cfg["bands"]["high"] else "moderate")
    sc = mv(today["score"], "%", method="recovery_composite.v1", as_of=as_of, status="stale" if stale else ("partial" if today["missing"] else "ok"),
            coverage=today["coverage"], confidence=today["confidence"], band=band, date=today["date"])
    return {"score": sc, "today": today, "history": hist, "normal_range": nr, "stale": stale,
            "by_day": {d: r["score"] for d, r in by_day.items()}}


def _date(s):
    from agame.timeutil import parse_date
    return parse_date(s)
