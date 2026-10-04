"""PWA assets: manifest, deterministic PNG icons (stdlib only), service worker."""

import json
import struct
import zlib
from pathlib import Path

from agame.paths import REPO_ROOT

ICON_THEMES = {
    "default": {"bg": (255, 107, 26), "bg2": (232, 67, 10), "fg": (255, 255, 255)},
    "dark": {"bg": (24, 24, 27), "bg2": (11, 11, 12), "fg": (252, 82, 0)},
    "light": {"bg": (255, 255, 255), "bg2": (238, 238, 242), "fg": (232, 74, 0)},
}
ICON_THEMES["orange"] = ICON_THEMES["default"]

# The AGame mark on a 100-unit tile: an "A" whose crossbar is a heartbeat line. web/app.js draws the same paths.
LOGO_LEGS = [(28, 78), (50, 22), (72, 78)]
LOGO_PULSE = [(17, 62), (35, 62), (41, 51), (49, 72), (55, 62), (83, 62)]
LOGO_LEG_W, LOGO_PULSE_W, LOGO_RADIUS = 10, 6.5, 23


def _png(width, height, pixel_fn):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel_fn(x, y))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def icon_png(size, theme="default", maskable=False):
    """The AGame mark on a rounded tile (full bleed and inset when maskable), antialiased."""
    t = ICON_THEMES.get(theme, ICON_THEMES["default"])
    k = size / 100.0
    inset = 0.8 if maskable else 1.0
    off = size * (1 - inset) / 2

    def pt(p):
        return (off + p[0] * k * inset, off + p[1] * k * inset)
    segs = [(pt(a), pt(b), LOGO_LEG_W * k * inset / 2) for a, b in zip(LOGO_LEGS, LOGO_LEGS[1:])]
    segs += [(pt(a), pt(b), LOGO_PULSE_W * k * inset / 2) for a, b in zip(LOGO_PULSE, LOGO_PULSE[1:])]
    r = 0 if maskable else LOGO_RADIUS * k

    def dist_seg(px, py, a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return ((px - ax - tt * dx) ** 2 + (py - ay - tt * dy) ** 2) ** 0.5

    def tile_cov(cx, cy):
        if r == 0:
            return 1.0
        qx = min(max(cx, r), size - r)
        qy = min(max(cy, r), size - r)
        d = ((cx - qx) ** 2 + (cy - qy) ** 2) ** 0.5
        return max(0.0, min(1.0, r - d + 0.5))

    def pix(x, y):
        cx, cy = x + 0.5, y + 0.5
        a = tile_cov(cx, cy)
        if a <= 0:
            return (0, 0, 0, 0)
        g = (cx + cy) / (2 * size)
        bg = [t["bg"][c] + (t["bg2"][c] - t["bg"][c]) * g for c in range(3)]
        cov = 0.0
        for p0, p1, hw in segs:
            cov = max(cov, min(1.0, max(0.0, hw - dist_seg(cx, cy, p0, p1) + 0.5)))
            if cov >= 1.0:
                break
        col = [round(bg[c] + (t["fg"][c] - bg[c]) * cov) for c in range(3)]
        return (col[0], col[1], col[2], round(255 * a))
    return _png(size, size, pix)


def manifest(snapshot):
    ui = (snapshot.get("profile") or {}).get("ui") or {}
    return {
        "name": "AGame",
        "short_name": "AGame",
        "description": "Private fitness dashboard built from Apple HealthKit data.",
        "start_url": "./fitness_dashboard.html#/today",
        "scope": "./",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0b0b0c",
        "theme_color": "#0b0b0c",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "categories": ["health", "fitness"],
        "x_agame_app_icon": ui.get("app_icon") or "default",
    }


def write_assets(out_dir, snapshot, cache_version):
    out = Path(out_dir)
    (out / "icons").mkdir(parents=True, exist_ok=True)
    theme = ((snapshot.get("profile") or {}).get("ui") or {}).get("app_icon") or "default"
    files = {
        "icons/icon-192.png": icon_png(192, theme),
        "icons/icon-512.png": icon_png(512, theme),
        "icons/icon-maskable-512.png": icon_png(512, theme, maskable=True),
        "icons/apple-touch-icon.png": icon_png(180, theme, maskable=True),
    }
    for rel, data in files.items():
        (out / rel).write_bytes(data)
    (out / "manifest.webmanifest").write_text(json.dumps(manifest(snapshot), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sw = (REPO_ROOT / "scripts" / "fitness_sw.js").read_text(encoding="utf-8").replace("__CACHE_VERSION__", cache_version)
    (out / "fitness_sw.js").write_text(sw, encoding="utf-8")
    return sorted(files) + ["manifest.webmanifest", "fitness_sw.js"]
