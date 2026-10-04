"""Strength statistics (volume, e1RM, PRs) and Muscular Load / Muscle Freshness.

Only exercise-level logs (strength.json) drive per-muscle numbers. A HealthKit strength
workout without exercise detail never produces trained muscles. Optional cardio mapping
(config) is labelled approximate.
"""

import math
from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import mean
from agame.values import mv


def e1rm(weight, reps):
    """Epley estimate; reps 1 returns the weight itself."""
    if not weight or not reps:
        return None
    if reps == 1:
        return float(weight)
    return weight * (1 + reps / 30.0)


def _sessions(ctx):
    out = []
    for s in (ctx.data.get("strength") or {}).get("sessions", []):
        dt = tu.local_dt(s["start"], ctx.tz)
        if dt > ctx.now:
            continue
        ss = dict(s)
        ss["_dt"], ss["_date"] = dt, dt.date()
        out.append(ss)
    out.sort(key=lambda s: (s["_dt"], s["id"]))
    return out


def _work_sets(ex):
    return [st for st in ex["sets"] if not st.get("warmup")]


@metric("strength.exercise_stats", unit="kg", method="epley_e1rm.v1", inputs=["strength.sessions"])
def exercise_stats(ctx):
    per = defaultdict(lambda: {"sessions": [], "best_e1rm": None, "heaviest": None, "max_reps": None, "best_set_volume": None,
                               "best_session_volume": None})
    for s in _sessions(ctx):
        for ex in s["exercises"]:
            info = ctx.exercise(ex["exercise_id"]) or {"name": ex["exercise_id"]}
            ws = _work_sets(ex)
            if not ws:
                continue
            vol = sum((st.get("weight_kg") or 0) * st["reps"] for st in ws)
            reps = sum(st["reps"] for st in ws)
            heavy = max((st.get("weight_kg") or 0) for st in ws)
            e1s = [e1rm(st.get("weight_kg"), st["reps"]) for st in ws if st.get("weight_kg")]
            best_e1 = max(e1s) if e1s else None
            p = per[ex["exercise_id"]]
            p["name"] = info.get("name", ex["exercise_id"])
            row = {"date": s["_date"].isoformat(), "session_id": s["id"], "volume_kg": round(vol, 1), "reps": reps, "sets": len(ws),
                   "heaviest_kg": heavy or None, "e1rm_kg": round(best_e1, 1) if best_e1 else None,
                   "avg_rpe": round(mean([st.get("rpe") for st in ws]), 1) if any(st.get("rpe") for st in ws) else None}
            p["sessions"].append(row)
            for key, val in (("best_e1rm", best_e1), ("heaviest", heavy or None), ("max_reps", max(st["reps"] for st in ws)),
                             ("best_set_volume", max((st.get("weight_kg") or 0) * st["reps"] for st in ws) or None), ("best_session_volume", vol or None)):
                if val is not None and (p[key] is None or val > p[key]["value"]):
                    p[key] = {"value": round(val, 1), "date": s["_date"].isoformat(), "session_id": s["id"]}
    out = {}
    for ex_id, p in per.items():
        sess = p["sessions"]
        last = sess[-1]
        prev = [r for r in sess[:-1] if r["e1rm_kg"]]
        trend = None
        if last["e1rm_kg"] and prev:
            trend = round(last["e1rm_kg"] - prev[-1]["e1rm_kg"], 1)
        out[ex_id] = {"id": ex_id, "name": p["name"], "sessions": sess[-60:], "count": len(sess), "best_e1rm": p["best_e1rm"],
                      "heaviest": p["heaviest"], "max_reps": p["max_reps"], "best_set_volume": p["best_set_volume"],
                      "best_session_volume": p["best_session_volume"], "last": last, "e1rm_change_vs_prev": trend,
                      "progression_hint": progression_hint(ctx, ex_id, sess)}
    return out


def progression_hint(ctx, ex_id, sess):
    """Rule-based: if the last session hit all reps at avg RPE <= 8, suggest +2.5 kg (or +1 rep for bodyweight)."""
    if not sess:
        return None
    last = sess[-1]
    if last["avg_rpe"] is None:
        return None
    if last["avg_rpe"] <= 8.0:
        if last["heaviest_kg"]:
            return {"action": "add_weight", "kg": 2.5, "text": f"Try {last['heaviest_kg'] + 2.5:g} kg"}
        return {"action": "add_reps", "reps": 1, "text": "Add 1 rep per set"}
    if last["avg_rpe"] >= 9.5:
        return {"action": "hold", "text": "Repeat the weight; RPE was very high"}
    return {"action": "hold", "text": f"Repeat {last['heaviest_kg']:g} kg" if last["heaviest_kg"] else "Repeat"}


def strength_prs(ctx, stats):
    prs = []
    for ex_id, st in stats.items():
        for key, label in (("best_e1rm", "Estimated 1RM"), ("heaviest", "Heaviest weight"), ("best_session_volume", "Session volume"),
                           ("best_set_volume", "Set volume"), ("max_reps", "Most reps in a set")):
            if st.get(key):
                prs.append({"exercise_id": ex_id, "exercise": st["name"], "record": key, "label": label, **st[key]})
    return prs


def _muscle_sets_by_day(ctx):
    """dict date -> dict muscle -> (sets_equivalent, rpe_weighted). Plus cardio mapping (approximate)."""
    mcfg = ctx.cfg["muscles"]
    out = defaultdict(lambda: defaultdict(float))
    approx = defaultdict(lambda: defaultdict(float))
    for s in _sessions(ctx):
        for ex in s["exercises"]:
            info = ctx.exercise(ex["exercise_id"])
            if not info:
                continue
            ws = _work_sets(ex)
            for st in ws:
                rpe_w = (st.get("rpe") or 8.0) / 10.0
                for m in info.get("primary", []):
                    out[s["_date"]][m] += 1.0 * rpe_w
                for m in info.get("secondary", []):
                    out[s["_date"]][m] += mcfg["secondary_weight"] * rpe_w
    if mcfg.get("cardio_mapping_enabled"):
        for w in ctx.workouts:
            groups = mcfg["cardio_mapping"].get(w["sport"]) or mcfg["cardio_mapping"].get(w["_family"])
            if not groups:
                continue
            eq = w["_dur"] / 600.0 * mcfg["cardio_sets_per_10min"]
            for m in groups:
                approx[w["_date"]][m] += eq
    return out, approx


@metric("muscles.load_freshness", method="muscle_acwr_and_decay.v1", inputs=["strength.sessions", "config.muscles.cardio_mapping"])
def muscle_status(ctx):
    mcfg = ctx.cfg["muscles"]
    strength_days, approx_days = _muscle_sets_by_day(ctx)
    has_logs = bool(strength_days)
    sessions = _sessions(ctx)
    out = {"has_exercise_logs": has_logs, "groups": {}, "cardio_mapping_enabled": bool(mcfg.get("cardio_mapping_enabled")),
           "calibration": {"load_min_sessions": mcfg["load_min_sessions"], "load_weeks": mcfg["load_weeks"], "freshness_min_sessions": mcfg["freshness_min_sessions"]}}
    hk_strength = [w for w in ctx.workouts if w["_family"] == "strength"]
    linked = {s.get("workout_id") for s in sessions}
    out["unlogged_strength_workouts"] = sum(1 for w in hk_strength if w["source_id"] not in linked and (ctx.d - w["_date"]).days <= 42)
    for m in mcfg["groups"]:
        weekly = []
        for k in range(mcfg["load_weeks"]):
            end = ctx.d - timedelta(days=7 * k)
            tot = sum(strength_days[d][m] + approx_days[d][m] for d in tu.daterange(end - timedelta(days=6), end))
            weekly.append(tot)
        acute = weekly[0]
        chronic = mean(weekly[1:]) if len(weekly) > 1 else None
        sess_hits = sum(1 for d, mm in strength_days.items() if mm.get(m) and (ctx.d - d).days < 7 * mcfg["load_weeks"])
        approx_only = sess_hits == 0 and any(approx_days[d].get(m) for d in approx_days if (ctx.d - d).days < 42)
        if sess_hits >= mcfg["load_min_sessions"] and chronic:
            ratio = acute / chronic if chronic else None
            a = mcfg["acwr"]
            if ratio is None:
                ls = "calibrating"
            elif ratio > a["overtraining"]:
                ls = "overtraining"
            elif ratio >= a["productive"]:
                ls = "productive"
            elif ratio >= a["detraining"]:
                ls = "maintaining"
            else:
                ls = "detraining"
        else:
            ratio, ls = None, ("approximate" if approx_only else "calibrating") if (sess_hits or approx_only) else "no_data"
        # freshness: exponentially decayed fatigue
        fatigue = 0.0
        last_trained = None
        recent_sessions = 0
        for d in sorted(set(strength_days) | set(approx_days)):
            amt = strength_days[d].get(m, 0) + approx_days[d].get(m, 0)
            if amt <= 0:
                continue
            hours = (ctx.d - d).days * 24 + 12
            fatigue += amt * math.exp(-hours / mcfg["freshness_tau_h"])
            last_trained = d
            if strength_days[d].get(m):
                recent_sessions += 1
        th = mcfg["freshness_thresholds"]
        if last_trained is None:
            fs = "no_data"
        elif recent_sessions < mcfg["freshness_min_sessions"] and not approx_only:
            fs = "calibrating"
        else:
            fs = "depleted" if fatigue >= th["depleted"] else ("fatigued" if fatigue >= th["fatigued"] else "recovered")
        out["groups"][m] = {"load_status": ls, "acwr": round(ratio, 2) if ratio else None, "sets_7d": round(acute, 1),
                            "sets_weekly_avg": round(chronic, 1) if chronic else None, "freshness": fs, "fatigue": round(fatigue, 2),
                            "last_trained": last_trained.isoformat() if last_trained else None, "approximate": approx_only}
    return out


def weekly_strength(ctx, weeks=12):
    out = []
    cur = tu.week_start(ctx.d, ctx.week_start)
    sessions = _sessions(ctx)
    for i in range(weeks - 1, -1, -1):
        ws = cur - timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        ss = [s for s in sessions if ws <= s["_date"] <= we]
        hk = [w for w in ctx.workouts if w["_family"] == "strength" and ws <= w["_date"] <= we]
        vol = sum((st.get("weight_kg") or 0) * st["reps"] for s in ss for ex in s["exercises"] for st in _work_sets(ex))
        sets = sum(len(_work_sets(ex)) for s in ss for ex in s["exercises"])
        out.append({"week": ws.isoformat(), "sessions": max(len(ss), len(hk)), "logged_sessions": len(ss), "volume_kg": round(vol),
                    "sets": sets, "minutes": round(sum(w["_dur"] for w in hk) / 60), "partial": ws == cur})
    return out


def session_list(ctx, limit=60):
    sessions = _sessions(ctx)
    by_wid = {s.get("workout_id"): s for s in sessions if s.get("workout_id")}
    out = []
    for w in reversed([w for w in ctx.workouts if w["_family"] == "strength"]):
        s = by_wid.get(w["source_id"])
        row = {"workout_id": w["source_id"], "date": w["_date"].isoformat(), "start": w["_start"].isoformat(), "duration_s": round(w["_dur"]),
               "avg_hr": w.get("avg_hr"), "name": (s or {}).get("name") or w.get("name"), "logged": bool(s)}
        if s:
            row["session_id"] = s["id"]
            row["exercises"] = [{"exercise_id": ex["exercise_id"], "name": (ctx.exercise(ex["exercise_id"]) or {}).get("name", ex["exercise_id"]),
                                 "sets": [{k: st.get(k) for k in ("reps", "weight_kg", "rpe", "rir", "warmup")} for st in ex["sets"]]}
                                for ex in s["exercises"]]
            row["volume_kg"] = round(sum((st.get("weight_kg") or 0) * st["reps"] for ex in s["exercises"] for st in _work_sets(ex)))
            row["sets"] = sum(len(_work_sets(ex)) for ex in s["exercises"])
            muscles = set()
            for ex in s["exercises"]:
                info = ctx.exercise(ex["exercise_id"]) or {}
                muscles |= set(info.get("primary", []))
            row["muscles"] = sorted(muscles)
        out.append(row)
        if len(out) >= limit:
            break
    # logs without a HealthKit workout
    for s in reversed(sessions):
        if s.get("workout_id") in {r["workout_id"] for r in out}:
            continue
        if len(out) >= limit:
            break
        out.append({"workout_id": None, "session_id": s["id"], "date": s["_date"].isoformat(), "start": s["_dt"].isoformat(),
                    "duration_s": None, "avg_hr": None, "name": s.get("name"), "logged": True,
                    "exercises": [{"exercise_id": ex["exercise_id"], "name": (ctx.exercise(ex["exercise_id"]) or {}).get("name", ex["exercise_id"]),
                                   "sets": [{k: st.get(k) for k in ("reps", "weight_kg", "rpe", "rir", "warmup")} for st in ex["sets"]]} for ex in s["exercises"]],
                    "volume_kg": round(sum((st.get("weight_kg") or 0) * st["reps"] for ex in s["exercises"] for st in _work_sets(ex))),
                    "sets": sum(len(_work_sets(ex)) for ex in s["exercises"]),
                    "muscles": sorted({m for ex in s["exercises"] for m in (ctx.exercise(ex["exercise_id"]) or {}).get("primary", [])})})
    out.sort(key=lambda r: r["start"], reverse=True)
    return out[:limit]
