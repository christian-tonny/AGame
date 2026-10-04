#!/usr/bin/env python3
"""Serve the AGame dashboard behind owner sign-in.

Usage:
  python3 scripts/fitness_server.py                 # production: needs AGAME_* env (see .env.example)
  python3 scripts/fitness_server.py --dev           # local only: 127.0.0.1, no sign-in
Options: --port N (default $PORT or 8080), --data-dir, --dist-dir
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.paths import data_dir, dist_dir  # noqa: E402
from agame.server import Config, serve  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev", action="store_true", help="local development: bind 127.0.0.1, no authentication")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--dist-dir", default=None)
    a = ap.parse_args(argv)
    cfg = Config(data_dir(a.data_dir), dist_dir(a.dist_dir), dev=a.dev, port=a.port)
    serve(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
