#!/usr/bin/env python3
"""Upload the current data files to a running AGame server (Railway) so it rebuilds.

Usage:
  AGAME_UPLOAD_TOKEN=... python3 scripts/push_snapshot.py --url https://agame.example.app [--data-dir DIR]

The server validates the files as a whole before writing them; a rejected upload changes
nothing. Prints the server's build status. Exit 0 ok/degraded, 1 failed or rejected.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.paths import DATA_FILES, data_dir  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="server base URL")
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args(argv)
    token = os.environ.get("AGAME_UPLOAD_TOKEN")
    if not token:
        print("error: AGAME_UPLOAD_TOKEN not set", file=sys.stderr)
        return 1
    ddir = data_dir(a.data_dir)
    files = {f: (ddir / f).read_text(encoding="utf-8") for f in DATA_FILES if (ddir / f).exists()}
    req = urllib.request.Request(a.url.rstrip("/") + "/api/snapshot", data=json.dumps({"files": files}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(json.dumps({"status": "rejected", "http": e.code, "body": e.read().decode()[:2000]}))
        return 1
    print(json.dumps({"status": res["build"]["status"], "exit_code": res["build"]["exit_code"], "degraded_reasons": res["build"].get("degraded_reasons")}))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
