"""Nutrition totals, protein progress, net energy and Nutrition Score (Bevel 2.0 style)."""

from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute.ctx import clamp, mean
from agame.values import mv

NUTRIENTS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg", "caffeine_mg")


def _meals(ctx):
    out = []
    for m in (ctx.data.get("nutrition") or {}).get("meals", []):
        dt = tu.local_dt(m["t"], ctx.tz)
        if dt > ctx.now:
            continue
        out.append((dt, m))
    out.sort(key=lambda r: (r[0], r[1]["id"]))
    return out


def connected(ctx):
    n = ctx.data.get("nutrition") or {}
    return bool(n.get("connected")) or bool(n.get("meals"))


@metric("nutrition.daily", method="nutrition_totals.v1", inputs=["nutrition.meals", "nutrition.water", "nutrition.caffeine"])
def daily_totals(ctx):
    days = defaultdict(lambda: {k: None for k in NUTRIENTS} | {"meals": 0, "food_groups": defaultdict(float), "micros": defaultdict(float), "per_meal": []})
    for dt, m in _meals(ctx):
        d = dt.date()
        row = days[d]
        row["meals"] += 1
        mt = {k: 0.0 for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
        for it in m["items"]:
            for k in NUTRIENTS:
                v = it.get(k)
                if v is not None:
                    row[k] = (row[k] or 0.0) + v
                    if k in mt:
                        mt[k] += v
            for g, v in (it.get("food_groups") or {}).items():
                row["food_groups"][g] += v
            for g, v in (it.get("micros") or {}).items():
                row["micros"][g] += v
        row["per_meal"].append({"id": m["id"], "t": dt.isoformat(), "meal": m.get("meal"), "name": m.get("name"), **{k: round(v, 1) for k, v in mt.items()},
                                "items": [it["name"] for it in m["items"]]})
    n = ctx.data.get("nutrition") or {}
    for w in n.get("water", []):
        dt = tu.local_dt(w["t"], ctx.tz)
        if dt <= ctx.now:
            days[dt.date()]["water_ml"] = days[dt.date()].get("water_ml", 0) + w["ml"]
    for c in n.get("caffeine", []):
        dt = tu.local_dt(c["t"], ctx.tz)
        if dt <= ctx.now:
            r = days[dt.date()]
            r["caffeine_mg"] = (r["caffeine_mg"] or 0) + c["mg"]
            cutoff = ctx.target("caffeine_cutoff")
            if cutoff and dt.strftime("%H:%M") > cutoff:
                r["caffeine_after_cutoff_mg"] = r.get("caffeine_after_cutoff_mg", 0) + c["mg"]
    hk_days = {}
    for t in n.get("daily_totals", []):
        d = tu.parse_date(t["date"])
        if d > ctx.d:
            continue
        r = days[d]
        for k in NUTRIENTS:
            if t.get(k) is not None:
                r[k] = (r[k] or 0.0) + t[k]
        if t.get("water_ml") is not None:
            r["water_ml"] = r.get("water_ml", 0) + t["water_ml"]
        for g, v in (t.get("micros") or {}).items():
            r["micros"][g] += v
        hk_days[d] = bool(t.get("partial"))
    status = {tu.parse_date(s["date"]): s["complete"] for s in n.get("day_status", [])}
    out = []
    for d in sorted(days):
        r = days[d]
        complete = status.get(d)
        if complete is None:
            complete = None if d >= ctx.d else (r["meals"] >= 3 or (d in hk_days and not hk_days[d]))
        row = {"date": d.isoformat(), **{k: (round(r[k], 1) if r[k] is not None else None) for k in NUTRIENTS},
               "meals": r["meals"], "water_ml": r.get("water_ml"), "caffeine_after_cutoff_mg": r.get("caffeine_after_cutoff_mg"),
               "food_groups": {k: round(v) for k, v in r["food_groups"].items()} or None, "micros": {k: round(v, 1) for k, v in r["micros"].items()} or None,
               "complete": complete, "per_meal": r["per_meal"]}
        if row["kcal"]:
            cals = {"protein_g": 4, "carbs_g": 4, "fat_g": 9}
            tot = sum((row[k] or 0) * c for k, c in cals.items())
            row["macro_pct"] = {k: round(100 * (row[k] or 0) * c / tot) for k, c in cals.items()} if tot else None
        out.append(row)
    return out


@metric("nutrition.score", unit="%", method="nutrition_score.v1", inputs=["nutrition.daily", "profile.targets"])
def score_day(ctx, row):
    cfg = ctx.cfg["nutrition"]
    w = cfg["weights"]
    comps = {}
    pt = ctx.target("protein_g")
    if pt and row.get("protein_g") is not None:
        comps["protein"] = clamp(row["protein_g"] / pt, 0, 1) * 100
    kt = ctx.target("kcal")
    if kt and row.get("kcal") is not None:
        comps["energy"] = clamp(100 - abs(row["kcal"] - kt) / kt * 200, 0, 100)
    ft = ctx.target("fiber_g")
    if ft and row.get("fiber_g") is not None:
        comps["fiber"] = clamp(row["fiber_g"] / ft, 0, 1) * 100
    if row.get("meals"):
        lo, hi = cfg["regular_meals_range"]
        comps["regularity"] = 100.0 if lo <= row["meals"] <= hi else 60.0
    if not comps:
        return None
    tw = sum(w[k] for k in comps)
    base = sum(comps[k] * w[k] for k in comps) / tw
    contributors = []
    fg = row.get("food_groups") or {}
    cc = cfg["contributors"]
    if fg:
        vt = ctx.target("vegetables_g")
        if vt and "vegetables_g" in fg:
            contributors.append({"id": "vegetables", "label": "Vegetables", "value": fg["vegetables_g"], "unit": "g",
                                 "points": round(clamp(fg["vegetables_g"] / vt, 0, 1) * cc["vegetables"]["max_points"], 1)})
        if "whole_grains_g" in fg:
            contributors.append({"id": "whole_grains", "label": "Whole grains", "value": fg["whole_grains_g"], "unit": "g",
                                 "points": round(clamp(fg["whole_grains_g"] / cc["whole_grains"]["target_g"], 0, 1) * cc["whole_grains"]["max_points"], 1)})
        if "red_meat_g" in fg:
            over = max(0.0, fg["red_meat_g"] - cc["red_meat"]["limit_g"])
            contributors.append({"id": "red_meat", "label": "Red meat", "value": fg["red_meat_g"], "unit": "g",
                                 "points": -round(clamp(over / cc["red_meat"]["limit_g"], 0, 1) * cc["red_meat"]["max_penalty"], 1)})
    if row.get("sodium_mg") is not None:
        over = max(0.0, row["sodium_mg"] - cc["sodium"]["limit_mg"])
        contributors.append({"id": "sodium", "label": "Sodium", "value": row["sodium_mg"], "unit": "mg",
                             "points": -round(clamp(over / cc["sodium"]["limit_mg"], 0, 1) * cc["sodium"]["max_penalty"], 1)})
    if row.get("sugar_g") is not None:
        over = max(0.0, row["sugar_g"] - cc["sugar"]["limit_g"])
        contributors.append({"id": "sugar", "label": "Sugar", "value": row["sugar_g"], "unit": "g",
                             "points": -round(clamp(over / cc["sugar"]["limit_g"], 0, 1) * cc["sugar"]["max_penalty"], 1)})
    total = clamp(base + sum(c["points"] for c in contributors), 0, 100)
    return {"score": round(total), "components": {k: round(v) for k, v in comps.items()}, "contributors": contributors,
            "missing_components": [k for k in w if k not in comps]}


def energy_out(ctx, d):
    a = ctx.daily("active_energy_kcal").get(d)
    r = ctx.daily("resting_energy_kcal").get(d)
    if a is None and r is None:
        return None
    return {"active": a, "resting": r, "total": (a or 0) + (r or 0), "partial": a is None or r is None}


def summary(ctx):
    if not connected(ctx):
        return {"connected": False, "status": "missing", "note": "Nutrition not connected"}
    days = daily_totals(ctx)
    for row in days:
        d = tu.parse_date(row["date"])
        row["score"] = score_day(ctx, row) if (d < ctx.d and row["complete"] is True) else None  # only finished, fully logged days
        eo = energy_out(ctx, d)
        row["energy_out"] = eo
        if eo and row.get("kcal") is not None:
            row["net_kcal"] = round(row["kcal"] - eo["total"])
            row["net_partial"] = bool(eo["partial"]) or row["complete"] is not True
    by_date = {r["date"]: r for r in days}
    today = by_date.get(ctx.d.isoformat())
    yday = by_date.get((ctx.d - timedelta(days=1)).isoformat())
    pt = ctx.target("protein_g")
    complete7 = [r for r in days if (ctx.d - tu.parse_date(r["date"])).days in range(1, 8) and r["complete"] is not False and r["protein_g"] is not None]
    protein = {
        "target": pt,
        "today": mv(today["protein_g"] if today else None, "g", kind="user_entered", status=None if today else "missing",
                    as_of=today["per_meal"][-1]["t"] if today and today["per_meal"] else None, partial_day=True),
        "yesterday": yday["protein_g"] if yday else None,
        "avg_7": round(mean([r["protein_g"] for r in complete7]), 1) if complete7 else None,
        "days_hit_7": sum(1 for r in complete7 if pt and r["protein_g"] >= pt) if pt else None,
        "days_logged_7": len(complete7),
        "per_meal_today": [{"meal": m["meal"], "protein_g": m["protein_g"], "t": m["t"]} for m in (today or {}).get("per_meal", [])],
    }
    recipes = (ctx.data.get("nutrition") or {}).get("recipes", [])
    scored = [r for r in days if r.get("score")]
    return {"connected": True, "status": "ok", "days": days[-120:], "today": today, "yesterday": yday, "protein": protein,
            "last_score": {"date": scored[-1]["date"], **scored[-1]["score"]} if scored else None,
            "quick": quick_meals(ctx),
            "targets": {k: ctx.target(k) for k in ("protein_g", "kcal", "carbs_g", "fat_g", "fiber_g", "water_ml", "caffeine_mg_max", "vegetables_g", "caffeine_cutoff")},
            "recipes": recipes, "favorites": (ctx.data.get("nutrition") or {}).get("favorites", []),
            "planned": [p for p in (ctx.data.get("nutrition") or {}).get("planned_meals", []) if p["date"] >= ctx.d.isoformat()],
            "glucose": glucose_overlay(ctx)}


def quick_meals(ctx, days=60, n=5):
    """Your own meals to log again in one tap: the latest distinct ones and the ones you eat most (last `days` days)."""
    groups = {}
    for dt, m in _meals(ctx):
        if (ctx.d - dt.date()).days > days or not m.get("items"):
            continue
        name = (m.get("name") or ", ".join(i["name"] for i in m["items"])).strip()
        key = name.lower()
        g = groups.setdefault(key, {"name": name, "count": 0})
        g["count"] += 1
        g.update(meal_id=m["id"], last=dt.isoformat(), meal=m.get("meal"),
                 kcal=round(sum(i.get("kcal") or 0 for i in m["items"])) if any(i.get("kcal") is not None for i in m["items"]) else None,
                 protein_g=round(sum(i.get("protein_g") or 0 for i in m["items"]), 1) if any(i.get("protein_g") is not None for i in m["items"]) else None)
    rows = list(groups.values())
    recent = sorted(rows, key=lambda g: g["last"], reverse=True)[:n]
    frequent = [g for g in sorted(rows, key=lambda g: (-g["count"], g["name"])) if g["count"] >= 2 and g not in recent][:n]
    return {"recent": recent, "frequent": frequent}


def glucose_overlay(ctx):
    pts = ctx.by_day("glucose_mg_dl")
    if not pts:
        return None
    last_day = max(pts)
    return {"date": last_day.isoformat(), "points": [{"t": dt.isoformat(), "v": v} for dt, v in pts[last_day]]}
