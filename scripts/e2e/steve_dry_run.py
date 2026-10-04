#!/usr/bin/env python3
"""Rehearse Steve's morning routine end to end on synthetic data, using only the public commands.

Morning 1 (2026-10-02): first install, backfill of all history up to that day.
Morning 2 (2026-10-03): normal daily batch.
Morning 2 again:        the same batch re-sent (must be a no-op).
Morning 3 (2026-10-04): sleep has not synced yet (must build, degraded, and say so).

For each morning: update_from_healthkit.py -> validate_data.py -> build_dashboard.py, then read
dist/build_report.json and dist/morning_summary.json like Steve would. Prints a JSON log and exits
non-zero if any step behaves differently from the runbook (docs/deployment.md).

  python3 scripts/e2e/steve_dry_run.py [--keep DIR]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from agame.synthetic import write_synthetic  # noqa: E402
from datetime import date  # noqa: E402

USER_FILES = ("profile.json", "goals.json", "plans.json", "strength.json", "journal.json", "load.json", "social.json",
              "health_records.json", "coach.json")


def day_of(rec, key):
    return (rec.get(key) or "")[:10]


def make_batch(src, upto, only=None, with_sleep=True):
    """Batch with every HealthKit record dated <= upto (or == only)."""
    def keep(d):
        return d == only if only else d <= upto
    m = json.loads((src / "metrics.json").read_text())
    sl = json.loads((src / "sleep.json").read_text())
    wo = json.loads((src / "workouts.json").read_text())
    bo = json.loads((src / "body.json").read_text())
    nu = json.loads((src / "nutrition.json").read_text())
    ro = json.loads((src / "routes.geojson").read_text())
    workouts = [w for w in wo["workouts"] if keep(day_of(w, "start"))]
    route_ids = {w.get("route_id") for w in workouts if w.get("route_id")}
    return {
        "batch_version": 1, "date": only or upto, "generated_at": f"{only or upto}T05:40:00+02:00", "source": "healthkit",
        "samples": {
            "metrics": {sid: [p for p in pts if keep((p.get("date") or p.get("t") or "")[:10])] for sid, pts in m["series"].items()},
            "sleep": [n for n in sl["nights"] if keep(n["date"])] if with_sleep else [],
            "workouts": workouts,
            "body": [b for b in bo["measurements"] if keep(day_of(b, "t"))],
            # only HealthKit records; meals/water logged in the app are user_entered and never travel in a batch
            "nutrition": {k: [x for x in nu.get(k, []) if keep(day_of(x, "t")) and x.get("kind") != "user_entered"] for k in ("meals", "water", "caffeine")},
            "routes": [f for f in ro["features"] if f["properties"]["id"] in route_ids],
        },
        "series_meta": m.get("series_meta") or {},
    }


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, cwd=SCRIPTS, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def tree_hash(d):
    h = hashlib.sha256()
    for p in sorted(Path(d).glob("*.json")) + sorted(Path(d).glob("*.geojson")):
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()[:16]


def morning(data, dist, batch_file, day, expect):
    log = {"date": day}
    code, out, err = run(["update_from_healthkit.py", "--date", day, "--input", str(batch_file), "--data-dir", str(data)])
    imp = json.loads(out) if out.strip().startswith("{") else {"raw": out + err}
    log["import"] = {"exit": code, "status": imp.get("status"), "added": {k: v for k, v in (imp.get("added") or {}).items() if v},
                     "skipped_duplicate": imp.get("skipped_duplicate"), "conflicts": len(imp.get("conflicts") or [])}
    code_v, out_v, _ = run(["validate_data.py", str(data), "--date", day, "--json"])
    log["validate"] = {"exit": code_v, "errors": len(json.loads(out_v).get("errors", [])) if out_v.strip() else None}
    code_b, _, err_b = run(["build_dashboard.py", "--date", day, "--data-dir", str(data), "--out", str(dist), "--quiet"])
    rep = json.loads((dist / "build_report.json").read_text())
    ms = json.loads((dist / "morning_summary.json").read_text()) if (dist / "morning_summary.json").exists() else {}
    log["build"] = {"exit": code_b, "status": rep["status"], "degraded_reasons": rep.get("degraded_reasons"), "data_status": rep.get("data_status")}
    log["morning_summary"] = {k: ms.get(k) for k in ("recovery", "sleep", "call", "action", "data_status") if k in ms} or ms
    problems = []
    for k, v in expect.items():
        section, field = k.split(".")
        if log[section][field] != v:
            problems.append(f"{day}: expected {k}={v!r}, got {log[section][field]!r}")
    log["problems"] = problems
    return log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", help="keep the working directory here instead of a temp dir")
    a = ap.parse_args()
    work = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="steve-dry-run-"))
    if work.exists() and a.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    src = write_synthetic(work / "phone", date(2026, 10, 4), missing_last_sleep=True)  # the "iPhone": HealthKit source of truth
    data, dist = work / "agame-data", work / "dist"
    shutil.copytree(ROOT / "data", data)  # fresh install: empty fixtures
    for f in USER_FILES:  # the owner's own settings and entries (made in the app, not by Steve), saved before morning 1
        obj = json.loads((src / f).read_text())
        obj["generated_at"] = obj["as_of"] = "2026-09-01T20:00:00+02:00"
        (data / f).write_text(json.dumps(obj))

    logs = []
    b1 = work / "batch-2026-10-02.json"
    b1.write_text(json.dumps(make_batch(src, "2026-10-02")))
    logs.append(morning(data, dist, b1, "2026-10-02", {"import.exit": 0, "import.status": "applied", "validate.exit": 0, "build.exit": 0}))

    b2 = work / "batch-2026-10-03.json"
    b2.write_text(json.dumps(make_batch(src, None, only="2026-10-03")))
    logs.append(morning(data, dist, b2, "2026-10-03", {"import.exit": 0, "import.status": "applied", "build.exit": 0}))

    before = tree_hash(data)
    rerun = morning(data, dist, b2, "2026-10-03", {"import.exit": 0, "import.status": "already_imported", "build.exit": 0})
    rerun["data_unchanged"] = tree_hash(data) == before
    if not rerun["data_unchanged"]:
        rerun["problems"].append("rerun changed the data directory")
    logs.append(rerun)

    b3 = work / "batch-2026-10-04.json"
    b3.write_text(json.dumps(make_batch(src, None, only="2026-10-04")))  # phone has no sleep for last night yet
    last = morning(data, dist, b3, "2026-10-04", {"import.exit": 0, "build.exit": 2, "build.status": "degraded"})
    if not any("sleep" in r for r in last["build"]["degraded_reasons"] or []):
        last["problems"].append("degraded build does not mention missing sleep")
    logs.append(last)

    problems = [p for lg in logs for p in lg["problems"]]
    print(json.dumps({"workdir": str(work), "mornings": logs, "ok": not problems}, indent=1))
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
