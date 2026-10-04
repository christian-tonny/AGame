"""Deterministic, evidence-backed insights: daily call, one action, helping/hurting factors,
correlations, activity summaries with concrete improvements, overtraining warning.

Every insight lists the exact numbers it relies on (`evidence`). Short text only.
No diagnosis language (enforced by a banned-phrases test).
"""

import math
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import mean, median, pearson, stdev
from agame.compute import recovery as recm


def _fmt_pace(s):
    if s is None:
        return "—"
    s = round(s)
    return f"{s // 60}:{s % 60:02d}"


def _fmt_min(m):
    if m is None:
        return "—"
    m = round(m)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


@metric("insights.overtraining", method="overtraining_flag.v1", inputs=["metrics.hrv_sdnn_ms", "load.pmc", "plans.compliance"])
def overtraining(ctx, pmc_today, week_sessions):
    cfg = ctx.cfg["load"]["overtraining"]
    if not cfg["enabled"]:
        return {"enabled": False, "active": False}
    hrv = recm.daily_hrv(ctx)
    recent = [math.log(v) for d, v in hrv.items() if 0 <= (ctx.d - d).days < cfg["window_days"]]
    base = [math.log(v) for d, v in hrv.items() if cfg["window_days"] <= (ctx.d - d).days < 60]
    hrv_z = None
    if len(recent) >= 3 and len(base) >= 14 and stdev(base):
        hrv_z = (mean(recent) - mean(base)) / stdev(base)
    tsb = pmc_today["tsb"] if pmc_today else None
    misses = None
    if week_sessions is not None:
        misses = sum(1 for s in week_sessions if s.get("ratio") is not None and s["ratio"] < cfg["execution_ratio_below"])
    signals = {
        "hrv_down": hrv_z is not None and hrv_z <= cfg["hrv_z_below"],
        "tsb_low": tsb is not None and tsb <= cfg["tsb_below"],
        "execution": (misses >= cfg["execution_misses"]) if misses is not None else None,
    }
    active = signals["hrv_down"] and signals["tsb_low"] and (signals["execution"] is not False)
    return {"enabled": True, "active": bool(active), "signals": signals,
            "evidence": {"hrv_z_7d": round(hrv_z, 2) if hrv_z is not None else None, "tsb": tsb, "execution_misses": misses},
            "note": None if signals["execution"] is not None else "No plan to compare execution against"}


@metric("insights.recommendation", method="daily_call.v1", inputs=["recovery.score", "load.pmc", "sleep.debt", "journal.activity_status"])
def recommendation(ctx, rec, pmc_today, ramp, sleep, status, today_sessions, ot, strain_yday=None, strain_range=None):
    rcfg = ctx.cfg["insights"]["recommendation"]
    factors = []
    score = rec["score"]["v"] if rec and rec.get("score") else None
    stale_rec = rec["score"]["status"] == "stale" if rec and rec.get("score") else False
    if score is not None:
        band = rec["score"].get("band")
        factors.append({"id": "recovery", "label": "Recovery", "value": score, "unit": "%",
                        "direction": "hurting" if score < rcfg["reduce_recovery_below"] else ("helping" if band == "high" else "neutral"),
                        "weight": abs(score - 50) / 50 + (0.5 if score < rcfg["reduce_recovery_below"] else 0), "stale": stale_rec})
    comps = (rec or {}).get("today", {}).get("components", {}) if rec else {}
    if "hrv" in comps:
        c = comps["hrv"]
        factors.append({"id": "hrv", "label": "HRV vs usual", "value": c["value"], "unit": "ms", "baseline": c["baseline"],
                        "delta_pct": c["delta_pct"], "direction": "helping" if c["z"] > 0.5 else ("hurting" if c["z"] < -0.5 else "neutral"), "weight": abs(c["z"])})
    if "rhr" in comps:
        c = comps["rhr"]
        factors.append({"id": "rhr", "label": "Resting HR vs usual", "value": c["value"], "unit": "bpm", "baseline": c["baseline"],
                        "delta": c["delta"], "direction": "helping" if c["z"] > 0.5 else ("hurting" if c["z"] < -0.5 else "neutral"), "weight": abs(c["z"])})
    ln = (sleep or {}).get("last_night")
    need = ((sleep or {}).get("need") or {}).get("v")
    if ln and ln.get("asleep_min") is not None and need:
        diff = ln["asleep_min"] - need
        factors.append({"id": "sleep", "label": "Sleep vs need", "value": round(ln["asleep_min"]), "unit": "min", "need": need, "delta": round(diff),
                        "direction": "hurting" if diff < -45 else ("helping" if diff >= 0 else "neutral"), "weight": abs(diff) / 60, "stale": bool(sleep.get("stale"))})
    debt = ((sleep or {}).get("debt") or {}).get("v")
    if debt is not None:
        factors.append({"id": "sleep_debt", "label": "Sleep debt", "value": round(debt), "unit": "min",
                        "direction": "hurting" if debt >= rcfg["reduce_sleep_debt_min"] / 2 else "neutral", "weight": debt / 120})
    if pmc_today:
        tsb = pmc_today["tsb"]
        factors.append({"id": "form", "label": "Form (TSB)", "value": round(tsb, 1), "unit": "",
                        "direction": "hurting" if tsb < rcfg["reduce_tsb_below"] else ("helping" if tsb > 5 else "neutral"), "weight": abs(tsb) / 20})
    if ramp is not None and ramp.get("ramp_warning"):
        factors.append({"id": "ramp", "label": "Fitness ramp", "value": ramp.get("ramp"), "unit": "/wk", "direction": "hurting", "weight": 1.0})
    if strain_yday is not None and strain_range:
        hi = strain_range["high"]
        factors.append({"id": "strain_yday", "label": "Yesterday's strain", "value": round(strain_yday), "unit": "%",
                        "direction": "hurting" if strain_yday > hi else "neutral", "weight": max(0, strain_yday - hi) / 20})
    st = (status or {}).get("status")
    if st and st != "normal":
        factors.append({"id": "status", "label": "Status", "value": st, "unit": None, "direction": "hurting", "weight": 3.0})
    if ot and ot.get("active"):
        factors.append({"id": "overtraining", "label": "Overtraining warning", "value": "active", "unit": None, "direction": "hurting", "weight": 3.0})

    call, why = "train", "Inputs within your normal range"
    if st in ("sick", "injured"):
        call, why = "rest", f"Status: {st}"
    elif score is not None and score < rcfg["rest_recovery_below"]:
        call, why = "rest", f"Recovery {score}% < {rcfg['rest_recovery_below']}%"
    elif ot and ot.get("active"):
        call, why = "reduce", "Overtraining warning"
    elif score is not None and score < rcfg["reduce_recovery_below"]:
        call, why = "reduce", f"Recovery {score}% < {rcfg['reduce_recovery_below']}%"
    elif pmc_today and pmc_today["tsb"] < rcfg["reduce_tsb_below"]:
        call, why = "reduce", f"Form {round(pmc_today['tsb'])} < {rcfg['reduce_tsb_below']}"
    elif debt is not None and debt >= rcfg["reduce_sleep_debt_min"]:
        call, why = "reduce", f"Sleep debt {round(debt)} min"
    elif st in ("traveling", "recovering"):
        call, why = "reduce", f"Status: {st}"
    planned = [s for s in today_sessions if s["type"] not in ("REST", "NPU")]
    if call == "train" and not planned:
        call = "rest_day" if any(s["type"] == "REST" for s in today_sessions) else "open"
    if score is None and not factors:
        call, why = "unknown", "Not enough data for a call"
    factors.sort(key=lambda f: (f["direction"] != "hurting", f["direction"] != "helping", -f.get("weight", 0)))
    return {"call": call, "why": why, "factors": factors, "planned": [s["title"] for s in planned], "stale_inputs": stale_rec}


def one_action(ctx, rec_call, sync, sleep, nutrition, today_sessions, weight, bedtime):
    icfg = ctx.cfg["insights"]
    planned = [s for s in today_sessions if s["type"] not in ("REST", "NPU")]
    if sync.get("overall") == "missing":
        return {"id": "no_data", "text": "Waiting for the first sync", "detail": f"{ctx.cfg['sync']['agent_name']}'s morning import fills this in", "kind": "data"}
    if sync.get("sleep_missing"):
        return {"id": "sync", "text": "Sleep not synced yet", "detail": "Check back after the morning sync", "kind": "data"}
    if rec_call["call"] == "rest":
        return {"id": "rest", "text": "Rest today", "detail": rec_call["why"], "kind": "recovery"}
    if rec_call["call"] == "reduce" and planned and planned[0]["type"] in ctx.cfg["plans"]["hard_types"]:
        dur = round((planned[0].get("duration_s") or 2700) * 0.8 / 60)
        return {"id": "swap", "text": f"Swap {planned[0]['title']} for an easy {dur} min", "detail": rec_call["why"], "kind": "training"}
    if nutrition and nutrition.get("connected"):
        p = nutrition["protein"]
        if p["target"] and p["yesterday"] is not None:
            short = p["target"] - p["yesterday"]
            if short >= p["target"] * icfg["protein_shortfall_pct"]:
                return {"id": "protein", "text": f"Protein {round(short)} g short yesterday", "detail": f"Target {round(p['target'])} g", "kind": "nutrition"}
    debt = ((sleep or {}).get("debt") or {}).get("v")
    if debt is not None and debt >= icfg["sleep_debt_action_min"] and bedtime:
        return {"id": "bedtime", "text": f"Bed by {bedtime}", "detail": f"Sleep debt {round(debt)} min", "kind": "sleep"}
    traj = (weight or {}).get("goal") or {}
    if traj.get("status") == "behind" and traj.get("required_kg_per_week") is not None and traj.get("actual_kg_per_week") is not None:
        return {"id": "weight", "text": f"Weight trend {traj['actual_kg_per_week']:+.2f} kg/wk", "detail": f"Need {traj['required_kg_per_week']:+.2f} kg/wk", "kind": "body"}
    if planned:
        s = planned[0]
        return {"id": "session", "text": f"{s['title']}", "detail": s.get("objective") or s.get("label"), "kind": "training"}
    return {"id": "move", "text": "Easy day: keep moving", "detail": None, "kind": "recovery"}


@metric("insights.helping_hurting", method="lagged_pearson_gated.v1", inputs=["sleep", "strain", "nutrition", "journal", "recovery.score"])
def helping_hurting(ctx, recovery_by_day, sleep_hist, strain_by_day, nutrition_days):
    icfg = ctx.cfg["insights"]
    min_n, min_r = icfg["correlation_min_n"], icfg["correlation_min_abs_r"]
    sleep_by = {tu.parse_date(h["date"]): h for h in sleep_hist}
    nut_by = {tu.parse_date(r["date"]): r for r in (nutrition_days or [])}
    steps = ctx.daily("steps")
    journal = (ctx.data.get("journal") or {}).get("entries", [])
    alcohol = {}
    habits = {}
    for e in journal:
        d = tu.parse_date(e["date"])
        if e["type"] == "alcohol":
            alcohol[d] = alcohol.get(d, 0) + (e.get("value") or 1)
        if e["type"] == "habit" and e.get("habit_id"):
            habits.setdefault(e["habit_id"], set()).add(d)
    mids = [h["midpoint_min"] for h in sleep_hist if h.get("midpoint_min") is not None]
    med_mid = median(mids)
    factors = {
        "sleep_duration": ("Sleep duration", "min", lambda d: (sleep_by.get(d) or {}).get("asleep_min")),
        "sleep_timing": ("Sleep timing off your usual", "min", lambda d: abs(sleep_by[d]["midpoint_min"] - med_mid) if (d in sleep_by and med_mid is not None) else None),
        "strain_prev": ("Previous day's strain", "%", lambda d: strain_by_day.get(d - timedelta(days=1))),
        "protein_prev": ("Previous day's protein", "g", lambda d: (nut_by.get(d - timedelta(days=1)) or {}).get("protein_g")),
        "late_caffeine": ("Caffeine after cutoff", "mg", lambda d: (nut_by.get(d - timedelta(days=1)) or {}).get("caffeine_after_cutoff_mg", 0) if (d - timedelta(days=1)) in nut_by else None),
        "steps_prev": ("Previous day's steps", "steps", lambda d: steps.get(d - timedelta(days=1))),
        "alcohol_prev": ("Alcohol the evening before", "drinks", lambda d: alcohol.get(d - timedelta(days=1), 0) if journal else None),
    }
    for hid, days in habits.items():
        name = next((h["name"] for h in (ctx.data.get("journal") or {}).get("habits", []) if h["id"] == hid), hid)
        factors[f"habit_{hid}"] = (name, "done", (lambda dd: (lambda d: 1 if (d - timedelta(days=1)) in dd else 0))(days))
    out = {}
    for win in (7, 30, 90):
        rows = []
        for fid, (label, unit, fn) in factors.items():
            xs, ys = [], []
            for d, r in recovery_by_day.items():
                if 0 <= (ctx.d - d).days < win:
                    x = fn(d)
                    if x is not None:
                        xs.append(x)
                        ys.append(r)
            r, n = pearson(xs, ys)
            row = {"id": fid, "label": label, "unit": unit, "n": n, "needed": min_n}
            if n < min_n or r is None:
                row["status"] = "insufficient"
            elif abs(r) < min_r:
                row.update({"status": "no_clear_effect", "r": round(r, 2)})
            else:
                hi = [y for x, y in zip(xs, ys) if x > median(xs)]
                lo = [y for x, y in zip(xs, ys) if x <= median(xs)]
                eff = (mean(hi) - mean(lo)) if hi and lo else None
                row.update({"status": "ok", "r": round(r, 2), "direction": "helping" if r > 0 else "hurting",
                            "effect_points": round(eff, 1) if eff is not None else None})
            rows.append(row)
        rows.sort(key=lambda x: (x["status"] != "ok", -abs(x.get("r") or 0)))
        out[str(win)] = rows
    return out


@metric("insights.activity_summary", method="activity_rules.v1", inputs=["activity.detail", "plans.compliance"])
def activity_insights(ctx, w, det, planned=None):
    acfg = ctx.cfg["activity"]
    row = det["row"]
    facts, improvements = [], []
    fam = row["family"]
    if fam == "run" and row.get("pace_s_per_km") and row.get("distance_m"):
        prior = [x for x in ctx.workouts if x["_family"] == "run" and x.get("distance_m") and 0 < (w["_date"] - x["_date"]).days <= 30]
        ref = median([x["_dur"] / x["distance_m"] * 1000 for x in prior])
        headline = f"{row['distance_m'] / 1000:.1f} km at {_fmt_pace(row['pace_s_per_km'])}/km"
        if ref:
            diff = row["pace_s_per_km"] - ref
            facts.append({"id": "pace_vs_30d", "text": f"{abs(round(diff))} s/km {'faster' if diff < 0 else 'slower'} than your 30-day median",
                          "evidence": {"pace": row["pace_s_per_km"], "median_30d": round(ref, 1)}})
    else:
        headline = f"{_fmt_min(row['duration_s'] / 60)} {row['sport'].replace('_', ' ')}"
    if row["load"]["v"] is not None:
        loads = [ctx._load_cache[x["source_id"]]["v"] for x in ctx.workouts if x["_family"] == fam and x["source_id"] in getattr(ctx, "_load_cache", {})
                 and ctx._load_cache[x["source_id"]]["v"] is not None and 0 < (w["_date"] - x["_date"]).days <= 30]
        if loads:
            m = median(loads)
            facts.append({"id": "load_vs_30d", "text": f"Load {round(row['load']['v'])} vs typical {round(m)}", "evidence": {"load": row["load"]["v"], "median_30d": round(m, 1)}})
    for e in det.get("efforts") or []:
        if e.get("pr"):
            facts.append({"id": f"pr_{e['distance_m']}", "text": f"PR: {_dist_label(e['distance_m'])} in {_fmt_dur(e['time_s'])}", "evidence": e})
    m = det.get("matched")
    if m and m.get("vs_prior_avg_s_per_km") is not None:
        v = m["vs_prior_avg_s_per_km"]
        facts.append({"id": "matched", "text": f"Same route: {abs(round(v))} s/km {'faster' if v < 0 else 'slower'} than your average ({m['count'] - 1} prior)",
                      "evidence": {"rank": m["rank"], "count": m["count"]}})
    if planned:
        facts.append({"id": "compliance", "text": {"as_planned": "Completed as planned", "partial": "Partly completed vs plan", "done": "Planned session done"}.get(planned.get("compliance"), "Planned session"),
                      "evidence": {"ratio": planned.get("ratio"), "planned_s": planned.get("duration_s"), "actual_s": planned.get("actual_duration_s")}})
    # improvements
    v = det.get("verdict")
    if v and v["verdict"] == "positive" and v["diff_pct"] > 3:
        improvements.append({"id": "fade", "text": f"Start ~{max(3, round(v['diff_pct'] * 1.5))} s/km slower; second half was {v['diff_pct']}% slower",
                             "evidence": v})
    easy = (planned or {}).get("type") in acfg["easy_types"] or not (set(w.get("tags") or []) & {"tempo", "intervals", "race", "test_5k", "threshold"})
    z = det.get("zones")
    if z and easy and fam == "run":
        tot = sum(x["s"] for x in z) or 1
        hi = sum(x["s"] for x in z[3:]) / tot * 100
        if hi > 15:
            improvements.append({"id": "easy_too_hard", "text": f"Easy run had {round(hi)}% in Z4+; keep it in Z1–Z2", "evidence": {"z4_plus_pct": round(hi)}})
    cad = row.get("avg_cadence") or w.get("avg_cadence")
    if fam == "run" and cad and cad < acfg["cadence_floor_spm"]:
        improvements.append({"id": "cadence", "text": f"Cadence {round(cad)} spm: try +5% with shorter steps", "evidence": {"cadence": cad}})
    dc = det.get("decoupling_pct")
    if dc is not None and dc > acfg["decoupling_warn_pct"]:
        improvements.append({"id": "decoupling", "text": f"HR drifted {dc}% against pace: fuel earlier, build aerobic base", "evidence": {"decoupling_pct": dc}})
    g = det.get("gap")
    if g and row.get("pace_s_per_km") and g["gap_s_per_km"] and row["pace_s_per_km"] - g["gap_s_per_km"] > 12:
        improvements.append({"id": "hills", "text": f"Hills cost {round(row['pace_s_per_km'] - g['gap_s_per_km'])} s/km: pace climbs by effort",
                             "evidence": {"pace": row["pace_s_per_km"], "gap": g["gap_s_per_km"]}})
    iv = det.get("intervals") or []
    if len(iv) >= 3:
        ps = [i["pace_s_per_km"] for i in iv]
        cv = stdev(ps) / mean(ps) * 100 if stdev(ps) else 0
        if cv > 4:
            improvements.append({"id": "interval_spread", "text": f"Rep paces varied {round(cv, 1)}%: start the first rep easier", "evidence": {"cv_pct": round(cv, 1), "reps": len(iv)}})
    return {"headline": headline, "facts": facts[:4], "improvements": improvements[:3]}


def _dist_label(m):
    named = {400: "400 m", 1000: "1 km", 1609.344: "1 mile", 5000: "5K", 10000: "10K", 21097.5: "Half marathon", 42195: "Marathon", 50000: "50K"}
    return named.get(m, f"{m / 1000:g} km")


def _fmt_dur(s):
    s = round(s)
    h, r = divmod(s, 3600)
    mi, se = divmod(r, 60)
    return f"{h}:{mi:02d}:{se:02d}" if h else f"{mi}:{se:02d}"


def morning_brief(ctx, rec, sleep, rec_call, today_sessions):
    """Two short lines max (Bevel 'Good morning' card), facts only."""
    parts = []
    if sleep and sleep.get("last_night") and not sleep.get("stale"):
        ln = sleep["last_night"]
        need = (sleep.get("need") or {}).get("v")
        parts.append(f"Slept {_fmt_min(ln['asleep_min'])}" + (f" of {_fmt_min(need)} needed" if need else ""))
    comps = ((rec or {}).get("today") or {}).get("components", {})
    if "hrv" in comps:
        parts.append(f"HRV {comps['hrv']['value']:g} ms ({comps['hrv']['delta_pct']:+.0f}% vs usual)")
    if "rhr" in comps:
        parts.append(f"RHR {comps['rhr']['value']:g} ({comps['rhr']['delta']:+.0f})")
    call_txt = {"train": "Train as planned", "reduce": "Go easier today", "rest": "Rest today", "rest_day": "Planned rest day",
                "open": "Nothing planned", "unknown": "Not enough data yet"}[rec_call["call"]]
    return {"line1": " · ".join(parts[:3]) if parts else None, "line2": call_txt}
