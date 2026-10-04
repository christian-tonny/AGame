"""Per-activity analysis, best efforts, records, matched runs and race predictions."""

import math
from collections import deque
from datetime import timedelta

from agame import timeutil as tu
from agame.compute import metric
from agame.compute import load as loadm
from agame.compute import privacy
from agame.compute.ctx import RUN_SPORTS, mean, median, sport_family
from agame.values import mv


# ----------------------------------------------------------------- stream helpers
def _clean(t, vals):
    if not t or not vals:
        return []
    return [(ti, v) for ti, v in zip(t, vals) if ti is not None and v is not None]


def interp_at(xs, ys, x):
    """Linear interpolation of y at x for increasing xs."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo] or 1.0
    return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / span


def resample_1s(pts):
    if len(pts) < 2:
        return []
    t0, t1 = int(pts[0][0]), int(pts[-1][0])
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [interp_at(xs, ys, t) for t in range(t0, t1 + 1)]


def best_effort_time(t, dist, D):
    """Fastest elapsed time (s) to cover D metres within one activity, interpolated. None if too short."""
    pts = _clean(t, dist)
    if len(pts) < 2 or pts[-1][1] - pts[0][1] < D:
        return None
    T = [p[0] for p in pts]
    X = [p[1] for p in pts]
    best = None
    i = 0
    for j in range(1, len(X)):
        while i + 1 < j and X[j] - X[i + 1] >= D:
            i += 1
        if X[j] - X[i] < D:
            continue
        # time at which distance X[j]-D was reached, between i and i+1
        target = X[j] - D
        if i + 1 <= j and X[i + 1] != X[i]:
            frac = (target - X[i]) / (X[i + 1] - X[i])
            frac = max(0.0, min(1.0, frac))
            ts = T[i] + frac * (T[i + 1] - T[i])
        else:
            ts = T[i]
        el = T[j] - ts
        if best is None or el < best:
            best = el
    return best


def best_window_avg(series_1s, window):
    if len(series_1s) < window:
        return None
    q = deque()
    s = 0.0
    best = None
    for v in series_1s:
        q.append(v)
        s += v
        if len(q) > window:
            s -= q.popleft()
        if len(q) == window:
            a = s / window
            if best is None or a > best:
                best = a
    return best


def minetti_cost(g):
    g = max(-0.45, min(0.45, g))
    return 155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6


def gap_factors(dist, elev, window_m):
    """Per-sample grade-adjustment factor cost(g)/cost(0) using grade over ±window/2 metres."""
    n = len(dist)
    f = [1.0] * n
    j0 = j1 = 0
    for i in range(n):
        while dist[j0] < dist[i] - window_m / 2 and j0 < i:
            j0 += 1
        while j1 < n - 1 and dist[j1] < dist[i] + window_m / 2:
            j1 += 1
        dd = dist[j1] - dist[j0]
        g = (elev[j1] - elev[j0]) / dd if dd > 5 else 0.0
        f[i] = minetti_cost(g) / 3.6
    return f


# ----------------------------------------------------------------- per-activity analysis
def _aligned(s, *keys):
    t = s.get("t") or []
    out = []
    for i in range(len(t)):
        row = [t[i]] + [((s.get(k) or [None] * len(t))[i]) for k in keys]
        if all(v is not None for v in row):
            out.append(row)
    return out


def splits(ctx, w, unit_m=1000.0):
    s = w.get("samples") or {}
    pts = _clean(s.get("t"), s.get("dist_m"))
    if len(pts) < 2 or pts[-1][1] < unit_m * 0.5:
        return []
    T, X = [p[0] for p in pts], [p[1] for p in pts]
    hrp = _clean(s.get("t"), s.get("hr"))
    elp = _clean(s.get("t"), s.get("elev_m"))
    out = []
    k = 1
    prev_t, prev_x = T[0], X[0]
    while True:
        target = X[0] + k * unit_m
        last = target > X[-1]
        if last:
            target = X[-1]
            if target - prev_x < 50:
                break
        tt = interp_at(X, T, target)
        dur = tt - prev_t
        d = target - prev_x
        hr = [h for ti, h in hrp if prev_t <= ti <= tt]
        el_a = interp_at([p[0] for p in elp], [p[1] for p in elp], prev_t) if elp else None
        el_b = interp_at([p[0] for p in elp], [p[1] for p in elp], tt) if elp else None
        out.append({"n": k, "distance_m": round(d, 1), "time_s": round(dur, 1), "pace_s_per_km": round(dur / d * 1000.0, 1) if d > 0 else None,
                    "avg_hr": round(mean(hr)) if hr else None, "elev_delta_m": round(el_b - el_a, 1) if elp else None, "partial": last})
        if last:
            break
        prev_t, prev_x = tt, target
        k += 1
        if k > 1000:
            break
    return out


def split_verdict(ctx, w):
    s = w.get("samples") or {}
    pts = _clean(s.get("t"), s.get("dist_m"))
    if len(pts) < 4:
        return None
    T, X = [p[0] for p in pts], [p[1] for p in pts]
    half = X[0] + (X[-1] - X[0]) / 2
    th = interp_at(X, T, half)
    first, second = th - T[0], T[-1] - th
    if first <= 0:
        return None
    diff = 100.0 * (second - first) / first
    thr = ctx.cfg["activity"]["split_verdict_pct"]
    verdict = "negative" if diff < -thr else ("positive" if diff > thr else "even")
    return {"verdict": verdict, "first_half_s": round(first), "second_half_s": round(second), "diff_pct": round(diff, 1)}


def gap_summary(ctx, w):
    s = w.get("samples") or {}
    rows = _aligned(s, "dist_m", "elev_m")
    if len(rows) < 10 or rows[-1][1] - rows[0][1] < 500:
        return None
    T, X, E = [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
    f = gap_factors(X, E, ctx.cfg["activity"]["gap_smoothing_m"])
    adj = 0.0
    for i in range(1, len(X)):
        adj += (X[i] - X[i - 1]) * (f[i] + f[i - 1]) / 2
    dur = T[-1] - T[0]
    if adj <= 0:
        return None
    return {"gap_s_per_km": round(dur / adj * 1000.0, 1), "pace_s_per_km": round(dur / (X[-1] - X[0]) * 1000.0, 1),
            "kind": "estimated", "method": "Minetti 2002 energy cost of gradient", "label": "approximate", "factors": f, "rows": rows}


def curve(ctx, w, key, durations):
    s = w.get("samples") or {}
    pts = _clean(s.get("t"), s.get(key))
    if len(pts) < 10:
        return None
    one = resample_1s(pts)
    out = []
    for d in durations:
        v = best_window_avg(one, d)
        if v is not None:
            out.append({"s": d, "v": round(v)})
    return out or None


def decoupling(ctx, w):
    s = w.get("samples") or {}
    rows = _aligned(s, "dist_m", "hr")
    if len(rows) < 20 or rows[-1][0] - rows[0][0] < 1800:
        return None
    mid = len(rows) // 2

    def ef(rs):
        dur = rs[-1][0] - rs[0][0]
        if dur <= 0:
            return None
        speed = (rs[-1][1] - rs[0][1]) / dur * 60.0
        hr = mean([r[2] for r in rs])
        return speed / hr if hr else None
    a, b = ef(rows[:mid]), ef(rows[mid:])
    if not a or not b:
        return None
    return round(100.0 * (a - b) / a, 1)


def detect_intervals(ctx, w):
    s = w.get("samples") or {}
    rows = _aligned(s, "dist_m")
    if len(rows) < 30:
        return []
    thr = loadm.effective_threshold_pace(ctx)
    speeds = []
    for i in range(1, len(rows)):
        dt = rows[i][0] - rows[i - 1][0]
        speeds.append((rows[i][0], (rows[i][1] - rows[i - 1][1]) / dt if dt > 0 else 0))
    sm = []
    for i in range(len(speeds)):
        win = [v for t, v in speeds[max(0, i - 2): i + 3]]
        sm.append((speeds[i][0], sum(win) / len(win)))
    cut = (1000.0 / thr["value"]) * 0.97 if thr else median([v for _, v in sm]) * 1.12
    hrp = _clean(s.get("t"), s.get("hr"))
    out, start = [], None
    for t, v in sm + [(sm[-1][0] + 1, 0)]:
        if v >= cut and start is None:
            start = t
        elif v < cut and start is not None:
            if t - start >= 60:
                d0 = interp_at([r[0] for r in rows], [r[1] for r in rows], start)
                d1 = interp_at([r[0] for r in rows], [r[1] for r in rows], t)
                hr = [h for ti, h in hrp if start <= ti <= t]
                out.append({"n": len(out) + 1, "start_s": start, "time_s": round(t - start), "distance_m": round(d1 - d0),
                            "pace_s_per_km": round((t - start) / max(1, d1 - d0) * 1000), "avg_hr": round(mean(hr)) if hr else None})
            start = None
    return out


def laps(ctx, w):
    ls = w.get("laps") or []
    s = w.get("samples") or {}
    hrp = _clean(s.get("t"), s.get("hr"))
    out = []
    for i, lp in enumerate(ls):
        dur = lp["end_s"] - lp["start_s"]
        hr = [h for ti, h in hrp if lp["start_s"] <= ti <= lp["end_s"]]
        out.append({"n": i + 1, "time_s": round(dur), "distance_m": lp.get("distance_m"), "label": lp.get("label"),
                    "pace_s_per_km": round(dur / lp["distance_m"] * 1000) if lp.get("distance_m") else None,
                    "avg_hr": round(mean(hr)) if hr else None})
    return out


def detail_series(ctx, w, gap=None):
    """Downsampled aligned streams for charts (≤ max_detail_points)."""
    s = w.get("samples") or {}
    t = s.get("t") or []
    if len(t) < 2:
        return None
    n = len(t)
    maxp = ctx.cfg["activity"]["max_detail_points"]
    idx = privacy.downsample(list(range(n)), maxp)
    dist = s.get("dist_m")
    pace = [None] * n
    if dist:
        for i in range(n):
            j0, j1 = max(0, i - 3), min(n - 1, i + 3)
            if dist[j1] is not None and dist[j0] is not None and t[j1] is not None and t[j0] is not None:
                dd, dt = dist[j1] - dist[j0], t[j1] - t[j0]
                if dd > 1 and dt > 0:
                    p = dt / dd * 1000.0
                    pace[i] = round(p, 1) if p < 1200 else None
    gapser = [None] * n
    if gap:
        rowt = {r[0]: k for k, r in enumerate(gap["rows"])}
        for i in range(n):
            k = rowt.get(t[i])
            if k is not None and pace[i] is not None:
                gapser[i] = round(pace[i] / gap["factors"][k], 1)
    out = {"t": [t[i] for i in idx]}
    for key, arr in (("dist_m", dist), ("hr", s.get("hr")), ("elev_m", s.get("elev_m")), ("cadence", s.get("cadence")),
                     ("power_w", s.get("power_w")), ("pace_s_per_km", pace), ("gap_s_per_km", gapser if gap else None),
                     ("gct_ms", s.get("gct_ms")), ("vo_cm", s.get("vo_cm")), ("stride_m", s.get("stride_m")), ("temp_c", s.get("temp_c"))):
        if arr and any(v is not None for v in arr):
            out[key] = [arr[i] if i < len(arr) else None for i in idx]
    return out


def map_lines(ctx, w):
    s = w.get("samples") or {}
    lat, lon = s.get("lat"), s.get("lon")
    pts = []
    if lat and lon:
        pts = [(a, b) for a, b in zip(lat, lon) if a is not None and b is not None]
    elif w.get("route_id"):
        for f in (ctx.data.get("routes") or {}).get("features", []):
            if f["properties"]["id"] == w["route_id"]:
                pts = [(c[1], c[0]) for c in f["geometry"]["coordinates"]]
    if len(pts) < 2:
        return None
    lines = privacy.apply(pts, privacy.privacy_settings(ctx))
    return privacy.round_lines(lines)


def has_gps(w):
    s = w.get("samples") or {}
    return bool(s.get("lat") and any(v is not None for v in s["lat"])) or bool(w.get("route_id"))


def pace_zone_time(ctx, w):
    pz = loadm.pace_zones(ctx)
    if not pz.get("zones") or w["_family"] != "run":
        return None
    s = w.get("samples") or {}
    rows = _aligned(s, "dist_m")
    if len(rows) < 10:
        return None
    secs = [0.0] * len(pz["zones"])
    for i in range(1, len(rows)):
        dt = rows[i][0] - rows[i - 1][0]
        dd = rows[i][1] - rows[i - 1][1]
        if dt <= 0 or dd <= 0:
            continue
        pace = dt / dd * 1000.0
        zi = 0
        for j, z in enumerate(pz["zones"]):
            if pace <= (z["slow"] or 10 ** 9):
                zi = j
        secs[zi] += min(dt, 30)
    return [{"name": z["name"], "slow": z["slow"], "fast": z["fast"], "s": round(v)} for z, v in zip(pz["zones"], secs)]


# ----------------------------------------------------------------- history-wide
@metric("activity.best_efforts", unit="s", method="sliding_window_distance.v1", inputs=["workouts.samples.dist_m"])
def all_best_efforts(ctx):
    """dict family -> distance_m -> list of efforts sorted fastest first."""
    if hasattr(ctx, "_best_efforts"):
        return ctx._best_efforts
    dists = ctx.cfg["activity"]["best_effort_distances_m"]
    out = {}
    for w in ctx.workouts:
        fam = w["_family"]
        if fam not in ("run", "ride", "swim"):
            continue
        s = w.get("samples") or {}
        if not s.get("dist_m"):
            continue
        for D in dists if fam == "run" else ([1000, 5000, 10000, 20000, 40000] if fam == "ride" else [100, 400, 1000, 1500]):
            if (w.get("distance_m") or 0) < D:
                continue
            tt = best_effort_time(s.get("t"), s.get("dist_m"), D)
            if tt:
                out.setdefault(fam, {}).setdefault(D, []).append({"workout_id": w["source_id"], "date": w["_date"].isoformat(), "time_s": round(tt, 1),
                                                                    "pace_s_per_km": round(tt / D * 1000.0, 1), "name": w.get("name")})
    for fam in out:
        for D in out[fam]:
            out[fam][D].sort(key=lambda e: (e["time_s"], e["date"]))
    ctx._best_efforts = out
    return out


def efforts_in_activity(ctx, w):
    be = all_best_efforts(ctx).get(w["_family"], {})
    out = []
    for D, efforts in sorted(be.items()):
        for rank, e in enumerate(efforts[:3]):
            if e["workout_id"] == w["source_id"]:
                out.append({"distance_m": D, "time_s": e["time_s"], "rank": rank + 1, "pr": rank == 0})
        mine = [e for e in efforts if e["workout_id"] == w["source_id"]]
        if mine and not any(o["distance_m"] == D for o in out):
            out.append({"distance_m": D, "time_s": mine[0]["time_s"], "rank": None, "pr": False})
    return out


@metric("activity.predictions", unit="s", method="riegel.v1", inputs=["activity.best_efforts"])
def predictions(ctx, before=None):
    cfg = ctx.cfg["activity"]
    end = before or ctx.d
    start = end - timedelta(days=cfg["prediction_window_days"])
    be = all_best_efforts(ctx).get("run", {})
    cands = []
    for D, efforts in be.items():
        if D < cfg["prediction_min_source_m"]:
            continue
        for e in efforts:
            dd = tu.parse_date(e["date"])
            if start <= dd < end + timedelta(days=0 if before else 1):
                cands.append((D, e))
    out = []
    for target in cfg["prediction_targets_m"]:
        if not cands:
            break
        # choose the source effort whose distance is closest to the target (log scale); fastest at that distance
        best_D = min({D for D, _ in cands}, key=lambda D: abs(math.log(target / D)))
        src = min((e for D, e in cands if D == best_D), key=lambda e: e["time_s"])
        pt = src["time_s"] * (target / best_D) ** cfg["riegel_exponent"]
        out.append({"distance_m": target, "time_s": round(pt), "pace_s_per_km": round(pt / target * 1000.0, 1),
                    "source": {"distance_m": best_D, "time_s": src["time_s"], "date": src["date"], "workout_id": src["workout_id"]},
                    "kind": "estimated", "method": f"Riegel (exponent {cfg['riegel_exponent']})"})
    return out


def _path(ctx, w):
    s = w.get("samples") or {}
    if s.get("lat") and s.get("lon"):
        return [(a, b) for a, b in zip(s["lat"], s["lon"]) if a is not None and b is not None]
    return []


def _resample_path(pts, n):
    if len(pts) < 2:
        return []
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + privacy.haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    L = cum[-1]
    if L <= 0:
        return []
    out = []
    j = 0
    for k in range(n):
        target = L * k / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j] or 1.0
        f = (target - cum[j]) / seg
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f))
    return out


@metric("activity.matched", method="route_fingerprint.v1", inputs=["workouts.samples.lat", "workouts.samples.lon", "workouts.distance_m"])
def matched_groups(ctx):
    if hasattr(ctx, "_matched"):
        return ctx._matched
    cfg = ctx.cfg["activity"]["match"]
    runs = [w for w in ctx.workouts if w["sport"] in RUN_SPORTS and w.get("distance_m")]
    shapes = {}
    for w in runs:
        p = _path(ctx, w)
        if len(p) >= 10:
            shapes[w["source_id"]] = _resample_path(p, cfg["shape_points"])
    matches = {w["source_id"]: [] for w in runs}
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            da, db = a["distance_m"], b["distance_m"]
            if abs(da - db) / max(da, db) > cfg["distance_tolerance"]:
                continue
            sa, sb = shapes.get(a["source_id"]), shapes.get(b["source_id"])
            if sa and sb:
                if privacy.haversine_m(sa[0][0], sa[0][1], sb[0][0], sb[0][1]) > 300:
                    continue
                md = mean([privacy.haversine_m(p[0], p[1], q[0], q[1]) for p, q in zip(sa, sb)])
                if md <= cfg["shape_max_mean_m"]:
                    matches[a["source_id"]].append((b["source_id"], "route"))
                    matches[b["source_id"]].append((a["source_id"], "route"))
            elif not sa and not sb and abs(da - db) / max(da, db) <= 0.03 and a.get("route_id") and a.get("route_id") == b.get("route_id"):
                matches[a["source_id"]].append((b["source_id"], "approximate"))
                matches[b["source_id"]].append((a["source_id"], "approximate"))
    ctx._matched = matches
    return matches


def matched_for(ctx, w):
    m = matched_groups(ctx).get(w["source_id"]) or []
    if not m:
        return None
    rows = []
    for wid, kind in m + [(w["source_id"], "self")]:
        o = ctx.workouts_by_id.get(wid)
        if not o:
            continue
        rows.append({"workout_id": wid, "date": o["_date"].isoformat(), "time_s": round(o["_dur"]),
                     "pace_s_per_km": round(o["_dur"] / o["distance_m"] * 1000.0, 1), "avg_hr": o.get("avg_hr"), "self": kind == "self", "match": kind})
    rows.sort(key=lambda r: r["date"])
    prior = [r for r in rows if r["date"] < w["_date"].isoformat()]
    rank = sorted(rows, key=lambda r: r["pace_s_per_km"]).index(next(r for r in rows if r["self"])) + 1
    vs_avg = None
    if prior:
        vs_avg = round(rows[-1]["pace_s_per_km"] - mean([r["pace_s_per_km"] for r in prior]), 1) if rows[-1]["self"] else None
    return {"count": len(rows), "rank": rank, "rows": rows[-20:], "match_kind": m[0][1], "vs_prior_avg_s_per_km": vs_avg}


# ----------------------------------------------------------------- composite
def row(ctx, w, strain_pct=None):
    sl = loadm.session_load(ctx, w)
    a = w.get("_ann") or {}
    dist = w.get("distance_m")
    pace = round(w["_dur"] / dist * 1000.0, 1) if dist and w["_family"] in ("run", "walk") else None
    speed = round(dist / w["_dur"] * 3.6, 2) if dist and w["_family"] == "ride" else None
    return {
        "id": w["source_id"], "name": a.get("title") or w.get("name") or w["sport"].replace("_", " ").title(), "sport": w["sport"], "family": w["_family"],
        "start": w["_start"].isoformat(), "date": w["_date"].isoformat(), "duration_s": round(w["_dur"]),
        "moving_s": w.get("moving_s"), "distance_m": dist, "pace_s_per_km": pace, "speed_kph": speed,
        "elevation_gain_m": w.get("elevation_gain_m"), "avg_hr": w.get("avg_hr"), "max_hr": w.get("max_hr"),
        "kcal": w.get("active_kcal"), "load": sl, "strain": strain_pct, "has_gps": has_gps(w),
        "private": bool(a.get("private")), "race": bool(a.get("race")) or "race" in (w.get("tags") or []),
        "rpe": a.get("rpe"), "feel": a.get("feel"), "tags": w.get("tags") or [], "source": w.get("source"),
    }


def detail(ctx, w):
    from agame.compute import strain as strainm
    ws = strainm.workout_strain(ctx, w)
    gap = gap_summary(ctx, w) if w["_family"] == "run" else None
    s = w.get("samples") or {}
    thr = loadm.effective_threshold_pace(ctx)
    ef = intensity = None
    dist = w.get("distance_m")
    if dist and w.get("avg_hr") and w["_dur"] > 0:
        spd = (1000.0 / gap["gap_s_per_km"]) if gap else dist / w["_dur"]
        ef = round(spd * 60.0 / w["avg_hr"], 3)
        if thr:
            intensity = round(100.0 * spd / (1000.0 / thr["value"]), 1)
    if intensity is None and w.get("avg_hr") and ctx.phys("lthr"):
        intensity = round(100.0 * w["avg_hr"] / ctx.phys("lthr"), 1)
    pw_curve = curve(ctx, w, "power_w", ctx.cfg["activity"]["power_curve_s"])
    out = {
        "row": row(ctx, w, ws),
        "zones": loadm.workout_zones(ctx, w),
        "pace_zones": pace_zone_time(ctx, w),
        "splits": splits(ctx, w) if w["_family"] in ("run", "walk") else [],
        "splits_mi": splits(ctx, w, 1609.344) if w["_family"] in ("run", "walk") else [],
        "verdict": split_verdict(ctx, w) if w["_family"] == "run" else None,
        "laps": laps(ctx, w),
        "intervals": detect_intervals(ctx, w) if w["_family"] == "run" else [],
        "segments": w.get("segments"),
        "gap": {k: v for k, v in gap.items() if k not in ("factors", "rows")} if gap else None,
        "hr_curve": curve(ctx, w, "hr", ctx.cfg["activity"]["hr_curve_s"]),
        "power_curve": pw_curve,
        "efficiency_factor": ef, "intensity_pct": intensity,
        "intensity_basis": ("threshold pace" if thr and dist else ("LTHR" if intensity is not None else None)),
        "decoupling_pct": decoupling(ctx, w),
        "efforts": efforts_in_activity(ctx, w),
        "matched": matched_for(ctx, w),
        "series": detail_series(ctx, w, gap),
        "map": map_lines(ctx, w),
        "weather": w.get("weather"),
        "end": w["_end"].isoformat(),
        "device": w.get("device"),
        "hr_recovery": next((v for dt, dd, v, _ in ctx.series("hr_recovery_bpm") if dt and abs((dt - w["_end"]).total_seconds()) < 900), None),
        "annotation": w.get("_ann"),
    }
    return out


@metric("records.all", method="records.v1", inputs=["activity.best_efforts", "workouts", "strength.sessions"])
def records(ctx, strength_prs=None):
    top_n = ctx.cfg["activity"]["top_n_efforts"]
    be = all_best_efforts(ctx)
    out = {"run": [], "ride": [], "swim": [], "strength": strength_prs or [], "longest": {}}
    for fam in ("run", "ride", "swim"):
        for D, efforts in sorted(be.get(fam, {}).items()):
            out[fam].append({"distance_m": D, "best": efforts[0], "top": efforts[:top_n]})
    for fam in ("run", "ride", "swim", "walk"):
        ws = [w for w in ctx.workouts if w["_family"] == fam and w.get("distance_m")]
        if ws:
            lg = max(ws, key=lambda w: w["distance_m"])
            out["longest"][fam] = {"workout_id": lg["source_id"], "distance_m": lg["distance_m"], "date": lg["_date"].isoformat(),
                                   "top": [{"workout_id": w["source_id"], "distance_m": w["distance_m"], "date": w["_date"].isoformat()}
                                           for w in sorted(ws, key=lambda w: -w["distance_m"])[:top_n]]}
    rides = [w for w in ctx.workouts if w["_family"] == "ride"]
    if rides:
        out["ride_elevation"] = max((w.get("elevation_gain_m") or 0, w["source_id"]) for w in rides)
    pcs = []
    for w in ctx.workouts:
        pc = curve(ctx, w, "power_w", ctx.cfg["activity"]["power_curve_s"])
        if pc:
            pcs.append((w, pc))
    if pcs:
        best = {}
        for w, pc in pcs:
            for p in pc:
                if p["s"] not in best or p["v"] > best[p["s"]]["v"]:
                    best[p["s"]] = {"s": p["s"], "v": p["v"], "workout_id": w["source_id"], "date": w["_date"].isoformat()}
        out["power"] = [best[k] for k in sorted(best)]
    return out
