#!/usr/bin/env python3
"""Build the AGame dashboard. One deterministic, non-interactive command.

Usage:
  python3 scripts/build_dashboard.py --date YYYY-MM-DD [--data-dir DIR] [--out DIR]

Validates every data file against schemas/, computes all metrics once, writes a
self-contained dist/fitness_dashboard.html plus PWA assets, and always writes
dist/build_report.json.

Exit codes:
  0  ok         – built from fresh data
  2  degraded   – built and published, but data is partial/stale (see degraded_reasons)
  1  failed     – invalid or impossible data, or a compute error; previous dist/ untouched
  3  usage error
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame import timeutil as tu  # noqa: E402
from agame.build import build  # noqa: E402
from agame.paths import data_dir, dist_dir  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="build date in the profile timezone (YYYY-MM-DD)")
    ap.add_argument("--data-dir", default=None, help="default: $AGAME_DATA_DIR or ./data")
    ap.add_argument("--out", default=None, help="default: $AGAME_DIST_DIR or ./dist")
    ap.add_argument("--quiet", action="store_true", help="print only the status line")
    args = ap.parse_args(argv)
    try:
        bdate = tu.parse_date(args.date)
    except ValueError:
        print(f"error: bad --date {args.date!r}", file=sys.stderr)
        return 3
    report = build(data_dir(args.data_dir), dist_dir(args.out), bdate)
    if args.quiet:
        print(f"{report['status']} {report['build_date']} exit={report['exit_code']}")
    else:
        short = {k: report[k] for k in ("status", "exit_code", "build_date", "degraded_reasons") if k in report}
        short["errors"] = report["errors"][:20]
        short["output_hash"] = report.get("output_hash")
        print(json.dumps(short, indent=1))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
