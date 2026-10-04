#!/usr/bin/env python3
"""One-time backfill from Apple Health's export (Health app > profile > Export All Health Data).

Usage:
  python3 scripts/import_apple_health_export.py export.zip [--data-dir DIR] [--timezone Africa/Kigali] [--dry-run]

Reads export.xml (streamed) and workout-routes/*.gpx: daily values, sleep stages, workouts with heart-rate samples
and routes. Safe to repeat: records already imported are skipped, and nothing duplicates what the agent sends.
Over HTTP: POST /api/import/apple-health-export (body = the zip). Prints a JSON summary.
Exit codes: 0 imported · 2 imported, some records left out (listed under "rejected") · 1 rejected, nothing written · 3 usage
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.apple_export import ExportError, run  # noqa: E402
from agame.importer import BatchError  # noqa: E402
from agame.paths import data_dir  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="export.zip, the unzipped folder, or export.xml")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--timezone", default=None, help="IANA name (default: profile timezone)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    ddir = data_dir(a.data_dir)
    if not ddir.is_dir() or not Path(a.export).exists():
        print(json.dumps({"status": "rejected", "error": "data dir or export not found"}))
        return 3
    try:
        summary, code = run(a.export, ddir, a.timezone, a.dry_run, progress=lambda m: print(m, file=sys.stderr))
    except (ExportError, BatchError, OSError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 1
    print(json.dumps(summary, indent=1, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
