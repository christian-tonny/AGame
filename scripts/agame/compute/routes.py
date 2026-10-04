"""Route library, personal heatmap (incl. night view), segments, leaderboard contract,
and integrity flags. All coordinates leaving this module pass through privacy.apply."""

import math
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from agame import timeutil as tu
from agame.compute import metric
from agame.compute import privacy
from agame.compute.ctx import mean, median


def route_length(f):
    c = f["geometry"]["coordinates"]
    return sum(privacy.haversine_m(c[i - 1][1], c[i - 1][0], c[i][1], c[i][0]) for i in range(1, len(c)))


def route_gain(f):
    c = f["geometry"]["coordinates"]
    if not c or len(c[0]) < 3:
        return None
    return sum(max(0.0, c[i][2] - c[i - 1][2]) for i in range(1, len(c)))


def elevation_profile(f, n=120):
    c = f["geometry"]["coordinates"]
    if not c or len(c[0]) < 3:
        return None
    cum = [0.0]
    for i in range(1, len(c)):
        cum.append(cum[-1] + privacy.haversine_m(c[i - 1][1], c[i - 1][0], c[i][1], c[i][0]))
    idx = privacy.downsample(list(range(len(c))), n)
    return [{"d": round(cum[i]), "e": round(c[i][2], 1)} for i in idx]


def _recent_run_pace(ctx):
    paces = [w["_dur"] / w["distance_m"] * 1000.0 for w in ctx.workouts
             if w["_family"] == "run" and w.get("distance_m") and (ctx.d - w["_date"]).days <= 60 and "intervals" not in (w.get("tags") or [])]
    return median(paces)


@metric("routes.library", method="route_library.v1", inputs=["routes.geojson", "workouts"])
def library(ctx):
    ps = privacy.privacy_settings(ctx)
    pace = _recent_run_pace(ctx)
    out = []
    for f in (ctx.data.get("routes") or {}).get("features", []):
        p = f["properties"]
        if p["kind"] != "route":
            continue
        L = route_length(f)
        gain = route_gain(f)
        runs = [w for w in ctx.workouts if w.get("route_id") == p["id"]]
        best = min(runs, key=lambda w: w["_dur"] / (w.get("distance_m") or L)) if runs else None
        est = None
        if pace:
            est = pace * L / 1000.0 + (gain or 0) * 6.0  # ~6 s per metre climbed (documented approximation)
        pts = [(c[1], c[0]) for c in f["geometry"]["coordinates"]]
        lines = privacy.round_lines(privacy.apply(pts, ps, trim_ends=False), max_points=300)
        out.append({"id": p["id"], "name": p.get("name"), "sport": p.get("sport"), "distance_m": round(L), "elevation_gain_m": round(gain) if gain is not None else None,
                    "surface": p.get("surface"), "difficulty": p.get("difficulty"), "favorite": bool(p.get("favorite")), "offline": bool(p.get("offline")),
                    "est_time_s": round(est) if est else None, "est_basis": "60-day median run pace + 6 s/m climb" if est else None,
                    "times_run": len(runs), "best": ({"workout_id": best["source_id"], "time_s": round(best["_dur"]), "date": best["_date"].isoformat()} if best else None),
                    "efforts": [{"workout_id": w["source_id"], "date": w["_date"].isoformat(), "time_s": round(w["_dur"]),
                                 "pace_s_per_km": round(w["_dur"] / (w.get("distance_m") or L) * 1000, 1)} for w in runs[-20:]],
                    "lines": lines, "profile": elevation_profile(f)})
    out.sort(key=lambda r: (not r["favorite"], r["name"] or ""))
    return out


def recommend(ctx, lib, target_m=None, surface=None):
    if not lib:
        return []
    target_m = target_m or (median([w.get("distance_m") for w in ctx.workouts if w["_family"] == "run" and w.get("distance_m")][-12:]) or 8000)
    def score(r):
        s = abs(r["distance_m"] - target_m) / target_m
        if surface and r.get("surface"):
            s += (100 - (r["surface"].get(f"{surface}_pct") or 0)) / 200.0
        s += 0.1 * min(r["times_run"], 10) / 10.0  # mild preference for variety
        return s
    return [{"route_id": r["id"], "name": r["name"], "distance_m": r["distance_m"], "why": f"Closest to {round(target_m / 1000, 1)} km"}
            for r in sorted(lib, key=score)[:3]]


# ----------------------------------------------------------------- solar (night view)
def sun_times(lat, lon, d):
    """NOAA sunrise equation (UTC). Returns (sunrise_utc, sunset_utc) or (None, None) at polar day/night."""
    n = d.toordinal() - datetime(2000, 1, 1).toordinal() + 0.0008
    js = n - lon / 360.0
    m = (357.5291 + 0.98560028 * js) % 360
    mr = math.radians(m)
    c = 1.9148 * math.sin(mr) + 0.02 * math.sin(2 * mr) + 0.0003 * math.sin(3 * mr)
    lam = math.radians((m + c + 180 + 102.9372) % 360)
    jt = 2451545.0 + js + 0.0053 * math.sin(mr) - 0.0069 * math.sin(2 * lam)
    dec = math.asin(math.sin(lam) * math.sin(math.radians(23.44)))
    cosw = (math.sin(math.radians(-0.83)) - math.sin(math.radians(lat)) * math.sin(dec)) / (math.cos(math.radians(lat)) * math.cos(dec))
    if cosw < -1 or cosw > 1:
        return None, None
    w = math.degrees(math.acos(cosw))
    jrise, jset = jt - w / 360.0, jt + w / 360.0

    def j2dt(j):
        return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=j - 2451545.0)
    return j2dt(jrise), j2dt(jset)


def is_night(lat, lon, dt):
    rise, sset = sun_times(lat, lon, dt.astimezone(timezone.utc).date())
    if rise is None:
        return False
    u = dt.astimezone(timezone.utc)
    return u < rise or u > sset


def _workout_points(w):
    s = w.get("samples") or {}
    if s.get("lat") and s.get("lon"):
        return [(a, b) for a, b in zip(s["lat"], s["lon"]) if a is not None and b is not None]
    return []


@metric("routes.heatmap", method="grid_heatmap.v1", inputs=["workouts.samples.lat", "workouts.samples.lon"])
def heatmap(ctx):
    cell = ctx.cfg["heatmap"]["cell_deg"]
    ps = privacy.privacy_settings(ctx)
    variants = defaultdict(lambda: defaultdict(int))
    n_acts = defaultdict(int)
    for w in ctx.workouts:
        pts = _workout_points(w)
        if not pts:
            continue
        night = is_night(pts[0][0], pts[0][1], w["_start"])
        age = (ctx.d - w["_date"]).days
        lines = privacy.apply(pts, ps)
        cells = set()
        for ln in lines:
            for lat, lon in ln:
                cells.add((round(lat / cell), round(lon / cell)))
        for rng, ok in (("all", True), ("365", age <= 365), ("90", age <= 90)):
            if not ok:
                continue
            for fam in ("all", w["_family"]):
                for nv in ("all", "night") if night else ("all",):
                    key = f"{rng}|{fam}|{nv}"
                    n_acts[key] += 1
                    for c in cells:
                        variants[key][c] += 1
    out = {}
    for key, cells in variants.items():
        top = sorted(cells.items(), key=lambda kv: (-kv[1], kv[0]))[:4000]
        out[key] = {"activities": n_acts[key], "cells": [[round(c[0] * cell, 5), round(c[1] * cell, 5), n] for c, n in top]}
    return {"cell_deg": cell, "variants": out, "status": "ok" if out else "missing"}


# ----------------------------------------------------------------- segments
@metric("routes.segments", unit="s", method="segment_match.v1", inputs=["routes.segments", "workouts.samples"])
def segments(ctx):
    scfg = ctx.cfg["segments"]
    ps = privacy.privacy_settings(ctx)
    out = []
    for f in (ctx.data.get("routes") or {}).get("features", []):
        p = f["properties"]
        if p["kind"] != "segment":
            continue
        coords = f["geometry"]["coordinates"]
        start, end = (coords[0][1], coords[0][0]), (coords[-1][1], coords[-1][0])
        L = route_length(f)
        efforts = []
        for w in ctx.workouts:
            s = w.get("samples") or {}
            lat, lon, t = s.get("lat"), s.get("lon"), s.get("t")
            if not lat or not lon:
                continue
            i = 0
            n = len(lat)
            while i < n:
                if lat[i] is not None and privacy.haversine_m(lat[i], lon[i], *start) <= scfg["match_radius_m"]:
                    # walk forward to the closest end point
                    path = 0.0
                    j = i + 1
                    found = None
                    while j < n and path <= L * (1 + scfg["length_tolerance"]) + 2 * scfg["match_radius_m"]:
                        if lat[j] is not None and lat[j - 1] is not None:
                            path += privacy.haversine_m(lat[j - 1], lon[j - 1], lat[j], lon[j])
                        if lat[j] is not None and privacy.haversine_m(lat[j], lon[j], *end) <= scfg["match_radius_m"] and abs(path - L) <= L * scfg["length_tolerance"] + scfg["match_radius_m"]:
                            found = j
                            break
                        j += 1
                    if found:
                        hr = [h for h in (s.get("hr") or [])[i:found + 1] if h is not None]
                        efforts.append({"workout_id": w["source_id"], "date": w["_date"].isoformat(), "time_s": t[found] - t[i],
                                        "avg_hr": round(mean(hr)) if hr else None})
                        i = found
                i += 1
        efforts.sort(key=lambda e: e["date"])
        pr = min(efforts, key=lambda e: e["time_s"]) if efforts else None
        lines = privacy.round_lines(privacy.apply([(c[1], c[0]) for c in coords], ps, trim_ends=False), max_points=150)
        board = [e for e in (ctx.data.get("social") or {}).get("segment_efforts", []) if e.get("segment_id") == p["id"]]
        out.append({"id": p["id"], "name": p.get("name"), "distance_m": round(L), "elevation_gain_m": round(route_gain(f) or 0),
                    "efforts": efforts[-50:], "count": len(efforts), "pr": pr, "lines": lines, "profile": elevation_profile(f, 60),
                    "leaderboard": board, "leaderboard_status": "connected" if board else "not_connected"})
    return out


@metric("routes.integrity", method="integrity_flags.v1", inputs=["workouts.samples"])
def integrity(ctx):
    """Flag GPS jumps and vehicle-like speeds in own activities (and imported competition data)."""
    flags = []
    for w in ctx.workouts:
        s = w.get("samples") or {}
        lat, lon, t = s.get("lat"), s.get("lon"), s.get("t")
        if not lat or not t:
            continue
        jumps, fast = 0, 0
        for i in range(1, len(lat)):
            if None in (lat[i], lat[i - 1], lon[i], lon[i - 1], t[i], t[i - 1]):
                continue
            dt = t[i] - t[i - 1]
            if dt <= 0:
                continue
            d = privacy.haversine_m(lat[i - 1], lon[i - 1], lat[i], lon[i])
            v = d / dt
            if d > 200 and v > 30:
                jumps += 1
            elif v > 12 and w["_family"] in ("run", "walk"):
                fast += dt
        if jumps or fast >= 30:
            flags.append({"workout_id": w["source_id"], "date": w["_date"].isoformat(), "gps_jumps": jumps, "vehicle_like_s": fast,
                          "status": "flagged", "reason": "GPS jump" if jumps else "Vehicle-like speed"})
    imported = (ctx.data.get("social") or {}).get("flags", [])
    return {"own": flags, "imported": imported, "checked": sum(1 for w in ctx.workouts if (w.get("samples") or {}).get("lat"))}
