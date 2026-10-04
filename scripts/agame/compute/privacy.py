"""Map privacy: hide points inside privacy zones and near the start/end of every trace.

Applied at build time to every coordinate that leaves Python (activity maps, routes,
heatmap, segments, share cards). Raw coordinates never reach the HTML.
"""

import math


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(min(1.0, math.sqrt(h)))


def privacy_settings(ctx):
    p = ctx.profile.get("privacy") or {}
    hide = p.get("hide_start_end_m")
    if hide is None:
        hide = ctx.cfg["privacy"]["default_hide_start_end_m"]
    return {"zones": p.get("zones") or [], "hide_start_end_m": hide}


def apply(points, settings, trim_ends=True):
    """points: list of (lat, lon[, extra...]). Returns list of visible polylines (lists of points)."""
    pts = [p for p in points if p[0] is not None and p[1] is not None]
    if not pts:
        return []
    keep = [True] * len(pts)
    for z in settings["zones"]:
        for i, p in enumerate(pts):
            if keep[i] and haversine_m(p[0], p[1], z["lat"], z["lon"]) <= z["radius_m"]:
                keep[i] = False
    hide = settings["hide_start_end_m"] or 0
    if trim_ends and hide > 0 and len(pts) > 1:
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
        total = cum[-1]
        for i in range(len(pts)):
            if cum[i] < hide or total - cum[i] < hide:
                keep[i] = False
    lines, cur = [], []
    for p, k in zip(pts, keep):
        if k:
            cur.append(p)
        elif cur:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return [ln for ln in lines if len(ln) >= 2]


def downsample(seq, n):
    if len(seq) <= n:
        return list(seq)
    step = (len(seq) - 1) / (n - 1)
    return [seq[round(i * step)] for i in range(n)]


def round_lines(lines, nd=5, max_points=400):
    total = sum(len(l) for l in lines) or 1
    out = []
    for ln in lines:
        budget = max(2, round(max_points * len(ln) / total))
        out.append([[round(p[0], nd), round(p[1], nd)] for p in downsample(ln, budget)])
    return out
