#!/usr/bin/env python3
"""Regenerate PWA assets (manifest, icons, service worker) for an existing dist/.

Normally build_dashboard.py does this. Usage:
  python3 scripts/fitness_pwa.py [--out dist/]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.paths import dist_dir  # noqa: E402
from agame.pwa import write_assets  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = dist_dir(a.out)
    html = out / "fitness_dashboard.html"
    if not html.exists():
        print(f"error: {html} not found; run build_dashboard.py first", file=sys.stderr)
        return 1
    version = hashlib.sha256(html.read_bytes()).hexdigest()[:16]
    files = write_assets(out, {"profile": {}}, version)
    print(json.dumps({"written": files, "cache_version": version}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
