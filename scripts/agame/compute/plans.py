"""Training calendar, plan-vs-actual compliance, adaptive plan suggestions, Workout Wizard,
instant workouts, Big Day Brief, routines and the Apple Watch export contract."""

from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute import load as loadm
from agame.compute.ctx import mean, median, sport_family
from agame.values import mv


def _type_label(ctx, t):
    return ctx.cfg["plans"]["type_labels"].get(t, t)


def template_sessions(ctx, start, days):
    """Sessions generated from the profile weekly template for days with nothing planned (kind computed)."""
    tmpl = {(t["weekday"]): t for t in (ctx.profile.get("schedule") or {}).get("template", [])}
    defaults = ctx.cfg["plans"]["default_session_by_intent"]
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        t = tmpl.get(tu.WEEKDAYS[d.weekday()])
        if not t:
            continue
        base = defaults.get(t["intent"], {"type": "XT", "sport": None, "duration_s": 3600})
        typ = t.get("type") or base["type"]
        out.append({"id": f"tmpl-{d.isoformat()}", "date": d.isoformat(), "type": typ, "sport": base["sport"],
                    "title": _type_label(ctx, typ) + (" (optional)" if t["intent"] == "optional_run" else ""),
                    "duration_s": t.get("duration_s") if t.get("duration_s") is not None else base["duration_s"],
                    "priority": "optional" if t["intent"] == "optional_run" else "normal", "steps": [], "guiding_metric": None,
                    "kind": "computed", "origin": "template", "status": "planned", "start_time": t.get("available_from")})
    return out


def planned_sessions(ctx, start, end):
    """Explicit plan sessions in [start, end], falling back to the template on days with none."""
    explicit = [dict(s, origin="plan") for s in (ctx.data.get("plans") or {}).get("sessions", [])
                if start.isoformat() <= s["date"] <= end.isoformat()]
    have = {s["date"] for s in explicit}
    gen = [s for s in template_sessions(ctx, start, (end - start).days + 1) if s["date"] not in have]
    return sorted(explicit + gen, key=lambda s: (s["date"], s.get("start_time") or "", s["id"]))


@metric("plans.compliance", method="plan_link_compliance.v1", inputs=["plans.sessions", "workouts"])
def link(ctx, sessions):
    """Attach linked workout + compliance to each past/today session; return (sessions, unplanned workout ids)."""
    pcfg = ctx.cfg["plans"]
    used = set()
    explicit_links = {s.get("linked_workout_id") for s in sessions if s.get("linked_workout_id")}
    for s in sessions:
        d = tu.parse_date(s["date"])
        s["label"] = _type_label(ctx, s["type"])
        if s["type"] == "REST":
            s["compliance"] = None
            continue
        w = None
        if s.get("linked_workout_id") and s["linked_workout_id"] in ctx.workouts_by_id:
            w = ctx.workouts_by_id[s["linked_workout_id"]]
        elif d <= ctx.d:
            fam = sport_family(s.get("sport") or "other")
            cands = [x for x in ctx.workouts_by_day.get(d, []) if x["source_id"] not in used and x["source_id"] not in explicit_links
                     and (x["_family"] == fam or s.get("sport") is None)]
            if cands and s.get("duration_s"):
                tol = pcfg["link_duration_tolerance"]
                cands = [x for x in cands if abs(x["_dur"] - s["duration_s"]) / s["duration_s"] <= tol] or cands[:1]
                w = min(cands, key=lambda x: abs(x["_dur"] - s["duration_s"]))
            elif cands:
                w = cands[0]
        if w:
            used.add(w["source_id"])
            sl = loadm.session_load(ctx, w)["v"]
            pl, _ = loadm.planned_load(ctx, s)
            ratio = None
            if s.get("load_planned") and sl:
                ratio = sl / s["load_planned"]
            elif s.get("duration_s"):
                ratio = w["_dur"] / s["duration_s"]
            lo, hi = pcfg["compliance_as_planned"]
            if ratio is None:
                c = "done"
            elif lo <= ratio <= hi:
                c = "as_planned"
            elif ratio >= pcfg["compliance_partial_min"]:
                c = "partial"
            else:
                c = "partial"
            s.update({"workout_id": w["source_id"], "actual_duration_s": round(w["_dur"]), "actual_load": sl, "planned_load": round(pl, 1) if pl else None,
                      "actual_distance_m": w.get("distance_m"), "ratio": round(ratio, 2) if ratio else None, "compliance": c})
        else:
            pl, how = loadm.planned_load(ctx, s)
            s["planned_load"] = round(pl, 1) if pl is not None else None
            if d < ctx.d:
                s["compliance"] = "skipped" if s.get("priority") == "optional" else "missed"
            else:
                s["compliance"] = "planned"
    linked = {s.get("workout_id") for s in sessions if s.get("workout_id")}
    return sessions, linked


def week_view(ctx, ws):
    we = ws + timedelta(days=6)
    sessions, linked = link(ctx, planned_sessions(ctx, ws, we))
    unplanned = []
    for d in tu.daterange(ws, min(we, ctx.d)):
        for w in ctx.workouts_by_day.get(d, []):
            if w["source_id"] not in linked:
                sl = loadm.session_load(ctx, w)["v"]
                unplanned.append({"id": f"npu-{w['source_id']}", "date": d.isoformat(), "type": "NPU", "label": "Unplanned", "sport": w["sport"],
                                  "title": w.get("name"), "workout_id": w["source_id"], "actual_duration_s": round(w["_dur"]), "actual_load": sl,
                                  "actual_distance_m": w.get("distance_m"), "compliance": "unplanned"})
    planned = [s for s in sessions if s["type"] != "REST"]
    actual_sessions = [s for s in planned if s.get("workout_id")] + unplanned
    header = {
        "planned": {"sessions": len(planned), "duration_s": sum(s.get("duration_s") or 0 for s in planned),
                    "load": round(sum(s.get("planned_load") or 0 for s in planned), 1)},
        "actual": {"sessions": len(actual_sessions), "duration_s": sum(s.get("actual_duration_s") or 0 for s in actual_sessions),
                   "load": round(sum(s.get("actual_load") or 0 for s in actual_sessions), 1)},
    }
    done = [s for s in planned if tu.parse_date(s["date"]) <= ctx.d]
    ok = [s for s in done if s.get("compliance") in ("as_planned", "done")]
    header["compliance_pct"] = round(100 * len(ok) / len(done)) if done else None
    return {"week": ws.isoformat(), "days": [(ws + timedelta(days=i)).isoformat() for i in range(7)],
            "sessions": sessions + unplanned, "header": header}


def calendar(ctx):
    """Month grid around the build date: activities, planned sessions and calendar events."""
    events = (ctx.data.get("plans") or {}).get("calendar", [])
    start = ctx.d.replace(day=1) - timedelta(days=35)
    end = ctx.d + timedelta(days=42)
    sessions, linked = link(ctx, planned_sessions(ctx, start, end))
    days = []
    for d in tu.daterange(start, end):
        acts = [{"id": w["source_id"], "sport": w["sport"], "family": w["_family"], "name": w.get("name"), "duration_s": round(w["_dur"]),
                 "distance_m": w.get("distance_m"), "planned": w["source_id"] in linked} for w in ctx.workouts_by_day.get(d, [])]
        ss = [s for s in sessions if s["date"] == d.isoformat()]
        ev = []
        for e in events:
            es, ee = tu.local_dt(e["start"], ctx.tz), tu.local_dt(e["end"], ctx.tz)
            if es.date() <= d <= ee.date():
                ev.append({"id": e["id"], "title": e["title"], "start": es.isoformat(), "end": ee.isoformat()})
        days.append({"date": d.isoformat(), "acts": acts, "sessions": ss, "events": ev})
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days}


def conflicts(ctx, sessions):
    events = (ctx.data.get("plans") or {}).get("calendar", [])
    tmpl = {t["weekday"]: t for t in (ctx.profile.get("schedule") or {}).get("template", [])}
    out = []
    for s in sessions:
        if s["type"] in ("REST",) or tu.parse_date(s["date"]) < ctx.d:
            continue
        d = tu.parse_date(s["date"])
        t = tmpl.get(tu.WEEKDAYS[d.weekday()]) or {}
        win_from, win_to = s.get("start_time") or t.get("available_from"), t.get("available_to")
        for e in events:
            if e.get("busy") is False:
                continue
            es, ee = tu.local_dt(e["start"], ctx.tz), tu.local_dt(e["end"], ctx.tz)
            if es.date() != d:
                continue
            if win_from and win_to:
                if es.strftime("%H:%M") < win_to and ee.strftime("%H:%M") > win_from:
                    out.append({"session_id": s["id"], "date": s["date"], "event": e["title"], "reason": f"Overlaps your usual {win_from}–{win_to} window"})
            else:
                out.append({"session_id": s["id"], "date": s["date"], "event": e["title"], "reason": "Calendar event on a training day"})
        if win_from and win_to and s.get("duration_s"):
            avail = (int(win_to[:2]) * 60 + int(win_to[3:])) - (int(win_from[:2]) * 60 + int(win_from[3:]))
            if s["duration_s"] / 60 > avail:
                out.append({"session_id": s["id"], "date": s["date"], "event": None, "reason": f"{round(s['duration_s'] / 60)} min planned, {avail} min available"})
    return out


# ----------------------------------------------------------------- guidance + alternatives
def guiding_metric(ctx, s):
    if s.get("guiding_metric"):
        return s["guiding_metric"]
    if s.get("sport") in (None, "strength"):
        return "rpe"
    if s["type"] in ctx.cfg["activity"]["easy_types"]:
        return "hr"
    if ctx.phys("ftp_w") and s.get("sport") in ("ride", "virtual_ride"):
        return "power"
    return "pace"


def targets_for(ctx, s):
    """Zone targets for a session type from configured zones."""
    hz = loadm.hr_zones(ctx).get("zones")
    pz = loadm.pace_zones(ctx).get("zones")
    zone_by_type = {"REC": 1, "AER": 2, "LR": 2, "TMP": 4, "THR": 4, "INT": 5, "VO2": 5, "RACE": 4}
    zi = zone_by_type.get(s["type"])
    out = {}
    if zi and hz and zi <= len(hz):
        out["hr"] = {"zone": zi, "low": hz[zi - 1]["low"], "high": hz[zi - 1]["high"]}
    if zi and pz and zi <= len(pz):
        out["pace"] = {"zone": zi, "slow": pz[zi - 1]["slow"], "fast": pz[zi - 1]["fast"]}
    return out


def pre_workout(ctx, s):
    gm = guiding_metric(ctx, s)
    return {"session_id": s["id"], "objective": s.get("objective") or _type_label(ctx, s["type"]), "guiding_metric": gm,
            "targets": targets_for(ctx, s), "steps": s.get("steps") or [],
            "watch": {"hr": "Stay under the top of the zone; walk hills if needed", "pace": "Hold the pace band; ignore HR drift late",
                      "power": "Hold the power band", "rpe": "Stop sets at the target RPE"}.get(gm)}


def wizard(ctx, s):
    """Workout Wizard: alternatives that change the rest of the week minimally."""
    if s["type"] == "REST" or not s.get("duration_s"):
        return []
    dur = s["duration_s"]
    pl, _ = loadm.planned_load(ctx, s)
    sport = s.get("sport")

    def alt(kind, typ, factor, title, note):
        nd = round(dur * factor / 60) * 60
        est = round(pl * factor * (0.75 if typ in ("REC", "AER") and s["type"] not in ("REC", "AER") else 1.0), 1) if pl else None
        return {"kind": kind, "type": typ, "label": _type_label(ctx, typ), "title": title, "duration_s": nd, "est_load": est, "note": note, "sport": sport}

    hard = s["type"] in ctx.cfg["plans"]["hard_types"]
    out = [
        alt("shorter", s["type"], 0.7, f"Shorter {_type_label(ctx, s['type']).lower()}", "Same intent, 30% less time"),
        alt("longer", s["type"], 1.2, f"Longer {_type_label(ctx, s['type']).lower()}", "Same intent, 20% more time"),
        alt("easier", "AER" if hard else "REC", 0.9, "Easier version", "Drop intensity one zone"),
        alt("harder", "TMP" if not hard else s["type"], 1.0, "Harder version", "Add 3 × 5 min at threshold" if not hard else "Add one more work rep"),
        alt("format", "INT" if s["type"] == "TMP" else ("TMP" if s["type"] in ("INT", "VO2") else s["type"]), 1.0, "Format change",
            "Same load, different structure"),
        alt("recovery", "REC", 0.6, "Recovery session", "Zone 1 only"),
    ]
    if sport == "strength":
        out = [alt("shorter", "STR", 0.6, "Shorter lift", "Main lifts only"), alt("easier", "STR", 0.8, "Lighter lift", "Cap RPE at 7"),
               alt("format", "MOB", 0.5, "Mobility instead", "Hips, ankles, thoracic"), alt("recovery", "REST", 0.0, "Rest", "Skip today")]
    return out


@metric("plans.instant_workouts", method="instant_workouts.v1", inputs=["workouts"])
def instant_workouts(ctx):
    runs = [w for w in ctx.workouts if w["_family"] == "run" and (ctx.d - w["_date"]).days <= 28]
    if len(runs) < 3:
        return {"status": "insufficient", "needed": 3, "have": len(runs), "options": []}
    avg_dur = median([w["_dur"] for w in runs])
    longest = max(w["_dur"] for w in runs)
    avg_dist = median([w.get("distance_m") or 0 for w in runs])
    fams = {w["_family"] for w in ctx.workouts if (ctx.d - w["_date"]).days <= 365}
    explore = next((f for f in ("ride", "swim", "walk") if f in fams), None)
    routes = sorted((f for f in (ctx.data.get("routes") or {}).get("features", []) if f["properties"]["kind"] == "route"),
                    key=lambda f: f["properties"]["id"])
    def pick_route(target_m):
        best = None
        from agame.compute.routes import route_length
        for f in routes:
            L = route_length(f)
            if best is None or abs(L - target_m) < abs(best[1] - target_m):
                best = (f["properties"]["id"], L, f["properties"].get("name"))
        return {"route_id": best[0], "name": best[2], "distance_m": round(best[1])} if best else None
    opts = [
        {"mode": "maintain", "title": "Easy run", "type": "AER", "duration_s": round(avg_dur / 60) * 60, "distance_m": round(avg_dist, -2),
         "why": f"Your 4-week median run is {round(avg_dur / 60)} min", "route": pick_route(avg_dist)},
        {"mode": "build", "title": "Longer run", "type": "LR", "duration_s": round(longest * 1.1 / 60) * 60,
         "why": f"10% beyond your longest recent run ({round(longest / 60)} min)", "route": pick_route(avg_dist * 1.4)},
        {"mode": "explore", "title": {"ride": "Easy ride", "swim": "Easy swim", "walk": "Hike"}.get(explore, "Trail run"),
         "type": "XT", "duration_s": 3600, "why": "Different stimulus, low impact" if explore else "New terrain from your library", "route": None},
        {"mode": "recover", "title": "Recovery jog", "type": "REC", "duration_s": 1800, "why": "Zone 1 only", "route": pick_route(4000)},
    ]
    return {"status": "ok", "options": opts}


def big_day(ctx, sessions, recovery_score, sleep_need):
    pcfg = ctx.cfg["plans"]
    out = []
    for s in sessions:
        d = tu.parse_date(s["date"])
        if d not in (ctx.d, ctx.d + timedelta(days=1)) or s["type"] == "REST":
            continue
        if (s.get("duration_s") or 0) >= pcfg["big_day_min_duration_s"] or s["type"] in ("LR", "RACE", "VO2", "INT", "THR", "TMP") and s.get("priority") == "key":
            wake = ctx.target("wake_time")
            bedtime = None
            if wake and sleep_need:
                wh, wm = int(wake[:2]), int(wake[3:])
                mins = (wh * 60 + wm - sleep_need - 15) % (24 * 60)
                bedtime = f"{mins // 60:02d}:{mins % 60:02d}"
            fuel = None
            if (s.get("duration_s") or 0) >= 5400:
                fuel = "Carb-focused dinner; 30–60 g carbs/h after the first hour"
            out.append({"session_id": s["id"], "date": s["date"], "when": "today" if d == ctx.d else "tomorrow", "title": s.get("title"),
                        "type": s["type"], "duration_s": s.get("duration_s"),
                        "evening": {"bedtime": bedtime, "sleep_need_min": sleep_need, "fuel": fuel, "kit": ["Shoes", "Watch charged", "Bottle/gels"] if s.get("sport") != "strength" else ["Lifting shoes", "Belt"]},
                        "morning": {"readiness": recovery_score, "targets": targets_for(ctx, s),
                                    "call": None if recovery_score is None else ("go" if recovery_score >= ctx.cfg["insights"]["recommendation"]["reduce_recovery_below"] else "adjust")}})
    return out


# ----------------------------------------------------------------- adaptation
def adaptations(ctx, week, recommendation, overtraining, status):
    """Rule-based suggested changes for the rest of the week. Each carries its reason; originals stay visible."""
    pcfg = ctx.cfg["plans"]
    out = []
    today = ctx.d.isoformat()
    rest_days_left = []
    future = [s for s in week["sessions"] if s["date"] >= today and s["type"] not in ("NPU",)]
    busy = {s["date"] for s in week["sessions"] if s["type"] not in ("REST",)}
    free_days = [d for d in week["days"] if d > today and d not in busy]
    st = (status or {}).get("status")
    if st in ("sick", "injured", "traveling", "recovering"):
        for s in future:
            if s["type"] in pcfg["hard_types"] or s.get("sport") == "strength":
                out.append({"session_id": s["id"], "date": s["date"], "action": "swap", "to": "REC" if st != "sick" else "REST",
                            "reason": f"Not feeling 100% · status: {st}", "rule": "status_restructure"})
        return out
    rec = (recommendation or {}).get("call")
    for s in future:
        if s["date"] != today:
            continue
        hard = s["type"] in pcfg["hard_types"]
        if rec == "rest":
            out.append({"session_id": s["id"], "date": s["date"], "action": "swap", "to": "REST" if s.get("sport") != "strength" else "MOB",
                        "reason": "Recovery very low", "rule": "low_recovery_rest"})
        elif rec in ("reduce", "swap") and hard:
            out.append({"session_id": s["id"], "date": s["date"], "action": "swap", "to": "AER", "reason": "Recovery below your reduce threshold",
                        "rule": "low_recovery_easier"})
        elif rec in ("reduce", "swap") and s.get("sport") == "strength":
            out.append({"session_id": s["id"], "date": s["date"], "action": "shorten", "factor": 0.7, "reason": "Lower recovery: main lifts only",
                        "rule": "strength_on_low_recovery"})
    if overtraining and overtraining.get("active"):
        for s in future:
            if s["type"] in pcfg["hard_types"] and s["date"] != today:
                out.append({"session_id": s["id"], "date": s["date"], "action": "swap", "to": "AER", "reason": "Overtraining warning active",
                            "rule": "overtraining"})
    for s in week["sessions"]:
        if s.get("compliance") == "missed" and s.get("priority") == "key" and free_days:
            out.append({"session_id": s["id"], "date": s["date"], "action": "move", "to_date": free_days[0],
                        "reason": "Key session missed; next free day", "rule": "reflow_missed"})
            free_days = free_days[1:]
    for s in future:
        t = s.get("forecast_temp_c")
        if t is not None and t >= pcfg["heat_adjust_from_c"] and s.get("sport") in ("run", "trail_run"):
            pct = (t - pcfg["heat_adjust_from_c"]) * pcfg["heat_adjust_pct_per_c"]
            out.append({"session_id": s["id"], "date": s["date"], "action": "adjust_pace", "pct_slower": round(pct, 1),
                        "reason": f"Forecast {t:g} °C", "rule": "heat"})
    return out


def pace_adjust_proposal(ctx):
    """Propose a threshold-pace change only after a consistent pattern across N tempo/threshold sessions."""
    pcfg = ctx.cfg["plans"]
    thr = loadm.effective_threshold_pace(ctx)
    if not thr:
        return None
    from agame.compute.activity import detect_intervals
    rows = []
    for w in reversed(ctx.workouts):
        if w["_family"] != "run":
            continue
        tags = set(w.get("tags") or [])
        if not tags & {"tempo", "threshold", "intervals"}:
            continue
        iv = detect_intervals(ctx, w)
        work = [i for i in iv if i["time_s"] >= 180]
        if work:
            rows.append(mean([i["pace_s_per_km"] for i in work]))
        if len(rows) >= pcfg["pace_adjust_min_sessions"]:
            break
    if len(rows) < pcfg["pace_adjust_min_sessions"]:
        return None
    faster = [100.0 * (thr["value"] - r) / thr["value"] for r in rows]
    if all(f >= pcfg["pace_adjust_min_pct"] for f in faster):
        return {"metric": "threshold_pace_s_per_km", "current": thr["value"], "proposed": round(thr["value"] * (1 - min(faster) / 100.0 / 2)),
                "reason": f"Last {len(rows)} threshold sessions averaged {round(min(faster), 1)}%+ faster than target", "sessions": len(rows)}
    return None


def race_context(ctx):
    races = [r for r in (ctx.data.get("plans") or {}).get("races", []) if r["date"] >= ctx.d.isoformat()]
    races.sort(key=lambda r: r["date"])
    out = []
    for r in races[:5]:
        days = (tu.parse_date(r["date"]) - ctx.d).days
        pr = r.get("priority") or "B"
        taper_days = {"A": 14, "B": 5, "C": 0}[pr]
        phase = "race_week" if days <= 7 else ("taper" if days <= taper_days else "build")
        out.append({**r, "days_to": days, "taper_days": taper_days, "phase": phase if taper_days else ("race_week" if days <= 2 else "build")})
    mode = (ctx.data.get("plans") or {}).get("mode") or ("race" if out else "maintain")
    return {"races": out, "mode": mode}


# ----------------------------------------------------------------- routines / watch export
def _wk_goal(step):
    if step.get("duration_s"):
        return {"type": "time", "value": step["duration_s"], "unit": "seconds"}
    if step.get("distance_m"):
        return {"type": "distance", "value": step["distance_m"], "unit": "meters"}
    return {"type": "open"}


def _wk_alert(step):
    t = step.get("target") or {}
    m = t.get("metric")
    if m == "hr":
        return {"type": "heartRateRange", "min": t.get("low"), "max": t.get("high")}
    if m == "pace":
        return {"type": "speedRange", "min_mps": round(1000.0 / t["high"], 3) if t.get("high") else None,
                "max_mps": round(1000.0 / t["low"], 3) if t.get("low") else None}
    if m == "power":
        return {"type": "powerRange", "min": t.get("low"), "max": t.get("high")}
    if m == "zone":
        return {"type": "heartRateZone", "zone": t.get("zone")}
    return None


@metric("plans.watch_export", method="workoutkit_shape.v1", inputs=["plans.routines"])
def watch_export(ctx, routine):
    """WorkoutKit-shaped custom workout (contract only: needs a companion app to install)."""
    steps = routine.get("steps") or []
    warm = next((s for s in steps if s["kind"] == "warmup"), None)
    cool = next((s for s in steps if s["kind"] == "cooldown"), None)
    blocks = []
    for s in steps:
        if s["kind"] == "repeat":
            blocks.append({"iterations": s.get("repeat") or 1,
                           "steps": [{"purpose": "work" if x["kind"] == "work" else "recovery", "goal": _wk_goal(x), "alert": _wk_alert(x), "label": x.get("label")}
                                     for x in s.get("steps") or []]})
        elif s["kind"] in ("work", "recovery"):
            blocks.append({"iterations": 1, "steps": [{"purpose": "work" if s["kind"] == "work" else "recovery", "goal": _wk_goal(s), "alert": _wk_alert(s), "label": s.get("label")}]})
    act = {"run": "running", "trail_run": "running", "ride": "cycling", "swim": "swimming", "row": "rowing"}.get(routine.get("sport"), "other")
    return {"contract": "agame.watch_workout.v1", "displayName": routine["name"], "activity": act, "location": "outdoor",
            "warmup": {"goal": _wk_goal(warm), "alert": _wk_alert(warm)} if warm else None, "blocks": blocks,
            "cooldown": {"goal": _wk_goal(cool), "alert": _wk_alert(cool)} if cool else None,
            "note": "Requires a companion app to install on Apple Watch; AGame does not sync by itself."}


def total_duration(steps):
    t = 0
    for s in steps or []:
        if s["kind"] == "repeat":
            t += (s.get("repeat") or 1) * total_duration(s.get("steps"))
        else:
            t += s.get("duration_s") or 0
    return t


def summary(ctx, recommendation=None, overtraining=None, recovery_score=None, sleep_need=None):
    ws = tu.week_start(ctx.d, ctx.week_start)
    this_week = week_view(ctx, ws)
    next_week = week_view(ctx, ws + timedelta(days=7))
    last_week = week_view(ctx, ws - timedelta(days=7))
    today_sessions = [s for s in this_week["sessions"] if s["date"] == ctx.d.isoformat() and s["type"] != "NPU"]
    tomorrow = [s for s in (this_week["sessions"] + next_week["sessions"]) if s["date"] == (ctx.d + timedelta(days=1)).isoformat() and s["type"] != "NPU"]
    upcoming = [s for s in this_week["sessions"] + next_week["sessions"] if s["date"] >= ctx.d.isoformat() and s["type"] not in ("NPU", "REST")]
    status = ctx.status_on(ctx.d)
    pl = ctx.data.get("plans") or {}
    routines = []
    for r in pl.get("routines", []):
        routines.append({**r, "total_duration_s": total_duration(r.get("steps")), "watch_export": watch_export(ctx, r)})
    return {
        "this_week": this_week, "next_week": next_week, "last_week": last_week,
        "today": [dict(s, pre=pre_workout(ctx, s), alternatives=wizard(ctx, s)) for s in today_sessions],
        "tomorrow": [dict(s, pre=pre_workout(ctx, s)) for s in tomorrow],
        "upcoming": [dict(s, alternatives=wizard(ctx, s)) for s in upcoming[:10]],
        "conflicts": conflicts(ctx, this_week["sessions"] + next_week["sessions"]),
        "adaptations": adaptations(ctx, this_week, recommendation, overtraining, status),
        "instant": instant_workouts(ctx),
        "big_day": big_day(ctx, this_week["sessions"] + next_week["sessions"], recovery_score, sleep_need),
        "pace_proposal": pace_adjust_proposal(ctx),
        "races": race_context(ctx),
        "plans": pl.get("plans", []), "templates": pl.get("templates", []), "routines": routines,
        "prehab": pl.get("prehab", []), "prehab_log": pl.get("prehab_log", []),
        "calendar": calendar(ctx),
        "has_explicit_plan": bool(pl.get("sessions")), "has_template": bool((ctx.profile.get("schedule") or {}).get("template")),
    }
