"""PWA assets: manifest, deterministic PNG icons (stdlib only), service worker."""

import json
import struct
import zlib
from pathlib import Path

from agame.paths import REPO_ROOT

ICON_THEMES = {
    "default": {"bg": (11, 11, 12), "fg": (252, 82, 0)},
    "light": {"bg": (243, 243, 245), "fg": (232, 74, 0)},
    "orange": {"bg": (252, 82, 0), "fg": (255, 255, 255)},
}


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
    """A rounded square with an upward chevron mark ('A')."""
    t = ICON_THEMES.get(theme, ICON_THEMES["default"])
    bg, fg = t["bg"], t["fg"]
    r = 0 if maskable else size * 0.22
    pad = size * (0.28 if maskable else 0.2)
    lw = size * 0.11

    def inside_round(x, y):
        cx, cy = x + 0.5, y + 0.5
        if r == 0:
            return True
        for ox, oy in ((r, r), (size - r, r), (r, size - r), (size - r, size - r)):
            if (cx < r or cx > size - r) and (cy < r or cy > size - r):
                if (cx - ox) ** 2 + (cy - oy) ** 2 > r * r and ((cx < r and ox == r) or (cx > size - r and ox == size - r)) and ((cy < r and oy == r) or (cy > size - r and oy == size - r)):
                    return False
        return True

    apex = (size / 2, pad)
    left = (pad, size - pad)
    right = (size - pad, size - pad)

    def dist_seg(px, py, a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        qx, qy = ax + tt * dx, ay + tt * dy
        return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5

    bar_y = size * 0.62

    def pix(x, y):
        if not inside_round(x, y):
            return (0, 0, 0, 0)
        cx, cy = x + 0.5, y + 0.5
        d = min(dist_seg(cx, cy, apex, left), dist_seg(cx, cy, apex, right))
        on = d <= lw / 2
        if not on and abs(cy - bar_y) <= lw / 2.4:
            # cross bar between the legs
            span = (cy - pad) / (size - 2 * pad)
            half = span * (size / 2 - pad)
            on = abs(cx - size / 2) <= half
        c = fg if on else bg
        return (c[0], c[1], c[2], 255)
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
