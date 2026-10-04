#!/usr/bin/env python3
"""Merge a HealthKit batch (JSON) into the AGame data directory. Idempotent.

Usage:
  python3 scripts/update_from_healthkit.py --date YYYY-MM-DD --input batch.json
  cat batch.json | python3 scripts/update_from_healthkit.py --date YYYY-MM-DD --input -
Options:
  --data-dir DIR   (default $AGAME_DATA_DIR or ./data)
  --dry-run        validate and report, write nothing

Prints a JSON summary on stdout.
Exit codes: 0 applied (or already imported), 2 applied but some records conflicted
(conflicting records were NOT applied), 1 rejected (malformed batch or invalid merged data;
nothing written), 3 usage error.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.importer import BatchError, apply_batch  # noqa: E402
from agame.paths import data_dir  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="the morning this batch is for (YYYY-MM-DD)")
    ap.add_argument("--input", required=True, help="batch file path, or - for stdin")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    ddir = data_dir(args.data_dir)
    if not ddir.is_dir():
        print(json.dumps({"status": "rejected", "error": f"data dir not found: {ddir}"}))
        return 3
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        batch = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "error": f"cannot read batch: {exc}"}))
        return 1
    if isinstance(batch, dict) and batch.get("date") and batch["date"] != args.date:
        print(json.dumps({"status": "rejected", "error": f"--date {args.date} does not match batch date {batch['date']}"}))
        return 1
    try:
        summary, code = apply_batch(ddir, batch, dry_run=args.dry_run)
    except BatchError as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 1
    print(json.dumps(summary, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
