#!/usr/bin/env python3
"""Run the unit/integration suite (test modules in parallel) and write dist/test_report.json.

Usage:
  python3 scripts/run_tests.py [--out dist/] [--jobs N]
Exit 0 when every test passes, 1 otherwise.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from agame.jsonio import atomic_write_text, canonical_dumps  # noqa: E402
from agame.paths import dist_dir  # noqa: E402


def run_module(name):
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "unittest", name], cwd=SCRIPTS / "tests", capture_output=True, text=True,
                       env=dict(os.environ, AGAME_QUIET="1"))
    out = p.stderr
    ran = int((re.search(r"Ran (\d+) tests?", out) or [0, 0])[1])
    fails = int((re.search(r"failures=(\d+)", out) or [0, 0])[1])
    errs = int((re.search(r"errors=(\d+)", out) or [0, 0])[1])
    skipped = int((re.search(r"skipped=(\d+)", out) or [0, 0])[1])
    problems = re.findall(r"^(?:FAIL|ERROR): (\S+) \((\S+)\)", out, re.M)
    return {"module": name, "tests": ran, "failures": fails, "errors": errs, "skipped": skipped, "ok": p.returncode == 0,
            "seconds": round(time.time() - t0, 1), "problems": [f"{b}.{a}" for a, b in problems],
            "tail": out.strip().splitlines()[-25:] if p.returncode else []}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    ap.add_argument("--jobs", type=int, default=max(2, min(8, os.cpu_count() or 2)))
    a = ap.parse_args(argv)
    mods = sorted(p.stem for p in (SCRIPTS / "tests").glob("test_*.py"))
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as ex:
        results = list(ex.map(run_module, mods))
    report = {"contract": "agame.test_report.v1", "status": "ok" if all(r["ok"] for r in results) else "failed",
              "tests": sum(r["tests"] for r in results), "failures": sum(r["failures"] for r in results), "errors": sum(r["errors"] for r in results),
              "skipped": sum(r["skipped"] for r in results), "wall_seconds": round(time.time() - t0, 1), "modules": results}
    out = dist_dir(a.out)
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out / "test_report.json", canonical_dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "tests", "failures", "errors", "skipped", "wall_seconds")}))
    for r in results:
        if not r["ok"]:
            print("\n".join(r["tail"]), file=sys.stderr)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
