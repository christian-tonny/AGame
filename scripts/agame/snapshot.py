"""Assemble computed.json: every metric computed once, in dependency order."""

from datetime import timedelta

from agame import SCHEMA_VERSION, __version__
from agame import timeutil as tu
from agame.compute import METRICS
from agame.compute import activity as actm
from agame.compute import body as bodym
from agame.compute import extras
from agame.compute import goals as goalsm
from agame.compute import insights as insm
from agame.compute import load as loadm
from agame.compute import muscles as musm
from agame.compute import nutrition as nutm
from agame.compute import plans as plansm
from agame.compute import recovery as recm
from agame.compute import routes as routesm
from agame.compute import sleep as sleepm
from agame.compute import strain as strainm
from agame.compute.ctx import Ctx, mean
from agame.values import mv

DETAIL_MAX_ACTIVITIES = 160


def _bedtime(ctx, need_min):
    wake = ctx.target("wake_time")
    if not wake or not need_min:
        return None
    wh, wm = int(wake[:2]), int(wake[3:])
    mins = (wh * 60 + wm - need_min - 15) % (24 * 60)
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _delta(cur, prev):
    if cur is None or prev is None:
        return None
    return round(cur - prev, 1)


def build_snapshot(data, build_date):
    ctx = Ctx(data, build_date)
    status = extras.data_status(ctx)

    # --- base daily metrics
    strain = strainm.strain_summary(ctx)
    sleep = sleepm.summary(ctx, strain["by_day"])
    rec = recm.summary(ctx, strain["by_day"])
    stress = strainm.stress_summary(ctx)
    sleep["recovery_correlation"] = sleepm.recovery_correlation(ctx, sleep["history"], rec["by_day"])

    # --- load
    pmc = loadm.pmc(ctx)
    pmc_today = loadm.pmc_today(ctx, pmc)
    cstatus = loadm.cardio_status(ctx, pmc)

    # --- plans (first pass for the daily call)
    ws = tu.week_start(ctx.d, ctx.week_start)
    week0 = plansm.week_view(ctx, ws)
    today_sessions = [s for s in week0["sessions"] if s["date"] == ctx.d.isoformat()]
    ot = insm.overtraining(ctx, pmc_today, [s for s in week0["sessions"] if s.get("ratio") is not None])
    status_today = ctx.status_on(ctx.d)
    strain_yday = strain["by_day"].get(ctx.d - timedelta(days=1))
    call = insm.recommendation(ctx, rec, pmc_today, cstatus, sleep, status_today, today_sessions, ot, strain_yday, strain["normal_range"])
    need_v = (sleep.get("need") or {}).get("v")
    plans = plansm.summary(ctx, call, ot, rec["score"]["v"], need_v)
    fc = loadm.forecast(ctx, pmc, plans["this_week"]["sessions"] + plans["next_week"]["sessions"] + [
        s for s in (ctx.data.get("plans") or {}).get("sessions", []) if s["date"] > (ws + timedelta(days=13)).isoformat()])

    # --- body / nutrition / strength
    weight = bodym.weight_summary(ctx)
    vo2 = bodym.vo2_summary(ctx)
    trends = bodym.all_metric_trends(ctx)
    nutrition = nutm.summary(ctx)
    ex_stats = musm.exercise_stats(ctx)
    prs = musm.strength_prs(ctx, ex_stats)
    muscles = musm.muscle_status(ctx)

    # --- energy
    eb = strainm.energy_bank(ctx, ctx.d, rec["score"]["v"] if not rec.get("stale") else None,
                             sleep["score"]["v"] if not sleep.get("stale") else None, stress.get("latest") if (stress.get("latest") or {}).get("date") == ctx.d.isoformat() else None)

    # --- goals
    best = actm.all_best_efforts(ctx)
    e1 = {k: {"value": v["best_e1rm"]["value"], "date": v["best_e1rm"]["date"]} for k, v in ex_stats.items() if v.get("best_e1rm")}
    streak = goalsm.weekly_streak(ctx)
    goals = goalsm.all_goals(ctx, {"best_efforts": best, "e1rm": e1, "weight": weight, "nutrition": nutrition, "streak": streak})

    # --- activities
    rows, details = [], {}
    linked = {}
    for wk in (plans["last_week"], plans["this_week"]):
        for s in wk["sessions"]:
            if s.get("workout_id"):
                linked[s["workout_id"]] = s
    cal_sessions = [s for d in plans["calendar"]["days"] for s in d["sessions"] if s.get("workout_id")]
    for s in cal_sessions:
        linked.setdefault(s["workout_id"], s)
    recent = ctx.workouts[-DETAIL_MAX_ACTIVITIES:]
    recent_ids = {w["source_id"] for w in recent}
    for w in reversed(ctx.workouts):
        r = actm.row(ctx, w, strainm.workout_strain(ctx, w))
        ps = linked.get(w["source_id"])
        r["planned"] = {"id": ps["id"], "type": ps["type"], "label": ps.get("label"), "compliance": ps.get("compliance")} if ps else None
        r["detail"] = w["source_id"] in recent_ids
        rows.append(r)
    for w in recent:
        det = actm.detail(ctx, w)
        ps = linked.get(w["source_id"])
        det["planned"] = ps
        det["insights"] = insm.activity_insights(ctx, w, det, ps)
        details[w["source_id"]] = det

    # --- routes / records
    lib = routesm.library(ctx)
    records = actm.records(ctx, prs)
    preds = actm.predictions(ctx)

    # --- insights
    helping = insm.helping_hurting(ctx, rec["by_day"], sleep["history"], strain["by_day"], nutrition.get("days"))
    action = insm.one_action(ctx, call, status, sleep, nutrition, today_sessions, weight, _bedtime(ctx, need_v))
    brief = insm.morning_brief(ctx, rec, sleep, call, today_sessions)

    # --- today block
    hrv_d = recm.daily_hrv(ctx)
    rhr_d = ctx.daily("resting_hr_bpm")
    prev_night = sleep["history"][-2] if len(sleep["history"]) >= 2 else None
    wpts = weight.get("points") or []
    since = {
        "hrv": {"v": round(hrv_d[ctx.d], 1) if ctx.d in hrv_d else None, "delta": _delta(hrv_d.get(ctx.d), hrv_d.get(ctx.d - timedelta(days=1))), "unit": "ms",
                "note": None if ctx.d in hrv_d else "No HRV this morning"},
        "rhr": {"v": round(rhr_d[ctx.d], 1) if ctx.d in rhr_d else None, "delta": _delta(rhr_d.get(ctx.d), rhr_d.get(ctx.d - timedelta(days=1))), "unit": "bpm",
                "note": None if ctx.d in rhr_d else "No resting HR this morning"},
        "sleep": {"v": (sleep.get("last_night") or {}).get("asleep_min") if not sleep.get("stale") else None,
                  "delta": _delta((sleep.get("last_night") or {}).get("asleep_min"), (prev_night or {}).get("asleep_min")) if not sleep.get("stale") else None,
                  "unit": "min", "note": "Sleep not synced yet" if sleep.get("stale") or sleep.get("last_night") is None else None},
        "weight": {"v": wpts[-1]["v"] if wpts else None, "delta": _delta(wpts[-1]["v"], wpts[-2]["v"]) if len(wpts) >= 2 else None, "unit": "kg",
                   "date": wpts[-1]["date"] if wpts else None, "note": None if wpts else "No weigh-ins"},
    }
    yday = [r for r in rows if r["date"] == (ctx.d - timedelta(days=1)).isoformat()]
    todays_acts = [r for r in rows if r["date"] == ctx.d.isoformat()]
    goals_strip = []
    for typ in ("body_weight", "distance", "record", "strength", "nutrition"):
        g = next((g for g in goals if g["type"] == typ), None)
        if g:
            goals_strip.append(g)
    today = {
        "date": ctx.d.isoformat(), "brief": brief, "recommendation": call, "action": action,
        "rings": {"strain": strain["score"], "recovery": rec["score"], "sleep": sleep["score"]},
        "energy": eb, "stress": stress["score"], "stress_latest": stress.get("latest"),
        "load": {"tsb": mv(pmc_today["tsb"] if pmc_today else None, "", method="pmc_ewma.v1", status=pmc["status"] if pmc_today else None),
                 "status": cstatus, "weekly_effort": loadm.weekly_effort(ctx)},
        "plan": plans["today"], "conflicts": [c for c in plans["conflicts"] if c["date"] == ctx.d.isoformat()],
        "adaptations": [a for a in plans["adaptations"] if a["date"] == ctx.d.isoformat()],
        "big_day": plans["big_day"], "since_yesterday": since, "yesterday": yday, "today_activities": todays_acts,
        "goals": goals_strip, "status": status_today, "overtraining": ot,
    }

    snap = {
        "meta": {
            "app": "AGame", "version": __version__, "schema_version": SCHEMA_VERSION, "build_date": ctx.d.isoformat(),
            "build_now": ctx.now.isoformat(), "timezone": ctx.tzname, "units": ctx.units, "week_start": ctx.week_start,
            "fixture": ctx.fixture, "data_status": status, "first_day": ctx.first_day.isoformat() if ctx.first_day else None,
            "metrics_registry": sorted(({"id": m["id"], "unit": m["unit"], "method": m["method"], "inputs": m["inputs"]} for m in METRICS.values()), key=lambda m: m["id"]),
            "detail_max_activities": DETAIL_MAX_ACTIVITIES,
        },
        "profile": _profile_view(ctx),
        "today": today,
        "recovery": {k: v for k, v in rec.items() if k != "by_day"},
        "sleep": sleep,
        "strain": {k: v for k, v in strain.items() if k != "by_day"},
        "stress": stress,
        "energy": eb,
        "training": {
            "pmc": pmc, "forecast": fc, "status": cstatus, "weekly_effort": today["load"]["weekly_effort"],
            "zone_distribution": loadm.zone_distribution(ctx), "log": goalsm.training_log(ctx), "progress": goalsm.progress(ctx),
            "predictions": preds, "hr_zones": loadm.hr_zones(ctx), "pace_zones": loadm.pace_zones(ctx),
            "threshold_candidates": loadm.threshold_candidates(ctx), "srpe": dict(zip(("k", "method", "pairs"), loadm.srpe_factor(ctx))),
        },
        "activities": {"list": rows, "details": details},
        "body": {"weight": weight, "vo2max": vo2, "metrics": trends,
                 "bp": {"systolic": trends.get("bp_systolic_mmhg"), "diastolic": trends.get("bp_diastolic_mmhg")},
                 "glucose_present": bool(ctx.series("glucose_mg_dl"))},
        "goals": goals, "streak": streak,
        "plans": plans,
        "strength": {"stats": ex_stats, "prs": prs, "muscles": muscles, "weekly": musm.weekly_strength(ctx), "sessions": musm.session_list(ctx),
                     "library": _library(ctx), "routines": (ctx.data.get("strength") or {}).get("routines", []),
                     "plates": (ctx.data.get("strength") or {}).get("plates") or {"bar_kg": None, "plates_kg": []},
                     "live_state": (ctx.data.get("strength") or {}).get("live_state")},
        "nutrition": nutrition,
        "routes": {"library": lib, "recommendations": routesm.recommend(ctx, lib), "heatmap": routesm.heatmap(ctx),
                   "segments": routesm.segments(ctx), "integrity": routesm.integrity(ctx),
                   "tiles": (ctx.profile.get("integrations") or {}).get("map_tiles_url"),
                   "attribution": (ctx.profile.get("integrations") or {}).get("map_attribution")},
        "records": records,
        "coach": {"helping_hurting": helping, "brief": brief, "recommendation": call,
                  "memory": (ctx.data.get("coach") or {}).get("memory", []), "checkins": (ctx.data.get("coach") or {}).get("checkins", []),
                  "threads": (ctx.data.get("coach") or {}).get("threads", [])[-20:], "settings": ctx.profile.get("coach") or {},
                  "last_maintenance": (ctx.data.get("coach") or {}).get("last_maintenance"),
                  "suggestions": _coach_suggestions(call, rec, nutrition, plans)},
        "timeline": extras.timeline(ctx, sleep, rec["history"]),
        "journal": extras.journal(ctx),
        "health": {"records": extras.health_records(ctx), "bioage": extras.bioage(ctx, sleep["history"])},
    }
    snap["social"] = extras.social(ctx, goals)
    snap["recaps"] = extras.recaps(ctx, sleep["history"], rec["history"], weight.get("points") or [], goals)
    week_start_last = (ws - timedelta(days=7)).isoformat()
    snap["records_week"] = [{"distance_m": D, **e} for D, effs in (best.get("run") or {}).items() for e in effs[:1]
                            if e["date"] >= week_start_last]
    snap["weekly_review"] = extras.weekly_review(ctx, snap)
    snap["widgets"] = _widgets(snap)
    return snap, ctx


def _library(ctx):
    lib = {x["id"]: dict(x, source="config") for x in ctx.library["exercises"]}
    for x in (ctx.data.get("strength") or {}).get("exercises", []):
        lib[x["id"]] = dict(x, source="user")
    return sorted(lib.values(), key=lambda x: x["name"])


def _profile_view(ctx):
    p = ctx.profile
    phys = p.get("physiology") or {}
    priv = p.get("privacy") or {}
    return {
        "display_name": (p.get("athlete") or {}).get("display_name"),
        "sex": (p.get("athlete") or {}).get("sex"), "birth_year": (p.get("athlete") or {}).get("birth_year"),
        "locale": p.get("locale") or {}, "physiology": phys, "zones_config": p.get("zones") or {},
        "schedule": (p.get("schedule") or {}).get("template", []), "targets": p.get("targets") or {},
        "privacy": {"hide_start_end_m": priv.get("hide_start_end_m"), "zones": [{"id": z["id"], "label": z.get("label"), "radius_m": z["radius_m"]} for z in priv.get("zones") or []],
                    "default_activity_private": priv.get("default_activity_private", False)},
        "modules": p.get("modules") or {}, "ui": p.get("ui") or {}, "integrations": {k: (bool(v) if k != "map_attribution" else v) for k, v in (p.get("integrations") or {}).items()},
        "coach": p.get("coach") or {}, "smart_alarm": p.get("smart_alarm") or {}, "beacon": {"enabled": (p.get("beacon") or {}).get("enabled", False),
                                                                                            "contacts": len((p.get("beacon") or {}).get("contacts") or [])},
        "auto_accept_thresholds": bool(p.get("auto_accept_thresholds")),
    }


def _coach_suggestions(call, rec, nutrition, plans):
    out = []
    if call["call"] in ("reduce", "rest"):
        out.append("Why is my recovery low?")
    out.append("Create a training plan")
    if nutrition.get("connected"):
        out.append("Log food")
    if plans.get("today"):
        out.append("What's the goal of today's session?")
    out.append("How is my fitness trending?")
    return out[:4]


def _widgets(snap):
    t = snap["today"]
    n = snap["nutrition"]
    return {
        "contract": "agame.widgets.v1",
        "rings": t["rings"], "energy": snap["energy"], "plan": [{"title": s.get("title"), "type": s["type"], "duration_s": s.get("duration_s")} for s in t["plan"]],
        "protein": (n.get("protein") or {}).get("today") if n.get("connected") else None, "protein_target": (n.get("protein") or {}).get("target") if n.get("connected") else None,
        "water_ml": (n.get("today") or {}).get("water_ml") if n.get("connected") else None, "water_target": (n.get("targets") or {}).get("water_ml") if n.get("connected") else None,
        "weight": snap["body"]["weight"].get("current"), "weight_goal": snap["body"]["weight"].get("goal"),
        "weekly_load": snap["training"]["weekly_effort"].get("current"), "weekly_band": snap["training"]["weekly_effort"].get("band"),
        "goal": t["goals"][0] if t["goals"] else None, "as_of": snap["meta"]["data_status"]["last_sync"],
    }
