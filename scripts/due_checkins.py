#!/usr/bin/env python3
"""List Coach check-ins due now, for the agent to deliver.

Reads coach.json → checkins ({type, time "HH:MM", days ["mon"...], text, enabled}) and prints the ones
whose scheduled time falls in the window ending now (default: the last 15 minutes), in the owner's time
zone. Each line carries the message and the computed facts it should include (from dist/morning_summary.json
or dist/weekly_review.json), so the agent never has to compute anything. Over HTTP: GET /api/agent/checkins.

Usage:
  python3 scripts/due_checkins.py [--data-dir DIR] [--dist DIR] [--now ISO] [--window-min 15]
Prints a JSON list. Exit 0.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame import checkins  # noqa: E402
from agame import timeutil as tu  # noqa: E402
from agame.datastore import load_all  # noqa: E402
from agame.paths import data_dir, dist_dir  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--dist", default=None)
    ap.add_argument("--now", default=None, help="ISO time with offset (default: now)")
    ap.add_argument("--window-min", type=int, default=15)
    a = ap.parse_args(argv)
    data, _, _ = load_all(data_dir(a.data_dir))
    tz = tu.tzinfo((data["profile"].get("locale") or {}).get("timezone") or tu.DEFAULT_TZ)
    now = tu.parse_ts(a.now).astimezone(tz) if a.now else datetime.now(tz)
    out = checkins.report(data["coach"].get("checkins", []), now, a.window_min, dist_dir(a.dist))["due"]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
