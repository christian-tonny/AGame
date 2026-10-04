#!/usr/bin/env python3
"""Validate AGame data files against checked-in schemas plus semantic rules.

Usage:
  python3 scripts/validate_data.py data/ [--date YYYY-MM-DD] [--json]

Exit codes: 0 valid, 1 invalid (errors printed), 3 usage error.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame import timeutil as tu  # noqa: E402
from agame.validate import validate_data  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir", nargs="?", default=None, help="data directory (default: $AGAME_DATA_DIR or ./data)")
    ap.add_argument("--date", help="build date YYYY-MM-DD; timestamps after it are rejected")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    from agame.paths import data_dir
    ddir = data_dir(args.data_dir)
    if not ddir.is_dir():
        print(f"error: data directory not found: {ddir}", file=sys.stderr)
        return 3
    bdate = tu.parse_date(args.date) if args.date else None
    rep, _ = validate_data(ddir, bdate)
    if args.json:
        print(json.dumps({"data_dir": str(ddir), **rep.as_dict()}, indent=1))
    else:
        for w in rep.warnings:
            print(f"warning: {w['file']}{w['pointer']}: {w['message']}")
        for e in rep.errors:
            print(f"ERROR:   {e['file']}{e['pointer']}: {e['message']}")
        print(f"{'OK' if rep.ok else 'INVALID'}: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s) in {ddir}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
