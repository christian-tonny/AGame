#!/usr/bin/env python3
"""Import a strength-app CSV export (Strong, Hevy, or a generic sets CSV) into strength.json.

Usage:
  python3 scripts/import_strength_csv.py export.csv [--data-dir DIR] [--map names.json] [--dry-run]

Each workout becomes one strength session (kind user_entered, source = the app name) with
exercise-level sets. Exercise names are matched to the library (config/exercises.json plus your
custom exercises in strength.json). Unknown names are reported and skipped: AGame never guesses
which muscles an exercise works. Pass --map with {"App exercise name": "exercise_id"} to map them.

Re-running is safe: a session already imported (same app, start time and name) is skipped.
Times without a zone are read in your profile time zone. Weights in lb are converted to kg.

Exit codes: 0 imported (or nothing new), 2 imported with skipped exercises, 1 rejected, 3 usage.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame import timeutil as tu  # noqa: E402
from agame.datastore import load_all  # noqa: E402
from agame.entries import EntryError, Store  # noqa: E402
from agame.paths import data_dir, load_exercise_library  # noqa: E402

LB = 0.45359237


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def detect(header):
    h = {norm(x) for x in header}
    if {"exercise title", "start time", "set index"} <= h:
        return "hevy"
    if {"exercise name", "set order", "date"} <= h:
        return "strong"
    if {"date", "exercise", "reps"} <= h:
        return "generic"
    raise ValueError("unrecognised CSV header; expected a Strong, Hevy or generic (date, exercise, reps[, weight_kg, rpe]) export")


def parse_time(s, tz):
    s = (s or "").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %b %Y, %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, f)
            return dt.replace(tzinfo=tz)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        raise ValueError(f"unreadable date/time {s!r}")


def num(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def rows_to_workouts(text, tz, unit):
    rd = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fmt = detect(rd.fieldnames or [])
    key = {norm(k): k for k in rd.fieldnames}
    g = lambda r, name: r.get(key.get(name, ""), "")
    workouts = OrderedDict()
    for r in rd:
        if fmt == "hevy":
            start, name, ex = g(r, "start time"), g(r, "title"), g(r, "exercise title")
            w = num(g(r, "weight kg"))
            if w is None and num(g(r, "weight lbs")) is not None:
                w = num(g(r, "weight lbs")) * LB
            warm = norm(g(r, "set type")) == "warmup"
            rpe = num(g(r, "rpe"))
        elif fmt == "strong":
            start, name, ex = g(r, "date"), g(r, "workout name"), g(r, "exercise name")
            w = num(g(r, "weight"))
            if w is not None and (unit == "lb" or "lb" in norm(" ".join(key))):
                w = w * LB
            warm = norm(g(r, "set order")) in ("w", "warm up", "warmup")
            rpe = num(g(r, "rpe"))
        else:
            start, name, ex = g(r, "date"), g(r, "workout") or "Imported workout", g(r, "exercise")
            w = num(g(r, "weight kg")) if "weight kg" in key else (num(g(r, "weight lb")) * LB if num(g(r, "weight lb")) is not None else None)
            warm = norm(g(r, "warmup")) in ("1", "true", "yes", "w")
            rpe = num(g(r, "rpe"))
        reps = num(g(r, "reps"))
        if reps is None or not ex:
            continue
        k = (start.strip(), name.strip())
        wk = workouts.setdefault(k, {"start": parse_time(start, tz), "name": name.strip() or None, "exercises": OrderedDict()})
        wk["exercises"].setdefault(ex.strip(), []).append({"reps": int(reps), "weight_kg": round(w, 2) if w is not None else None,
                                                           "rpe": rpe if rpe and 1 <= rpe <= 10 else None, "rir": None, "warmup": bool(warm)})
    return fmt, list(workouts.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--map", default=None, help="JSON object mapping app exercise names to exercise ids")
    ap.add_argument("--unit", choices=["kg", "lb"], default="kg", help="unit of the Strong 'Weight' column (default kg)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    ddir = data_dir(a.data_dir)
    if not ddir.is_dir():
        print(json.dumps({"status": "rejected", "error": f"data dir not found: {ddir}"}))
        return 3
    data, problems, _ = load_all(ddir)
    if problems:
        print(json.dumps({"status": "rejected", "error": "data dir unreadable", "problems": problems}))
        return 1
    tz = tu.tzinfo((data["profile"].get("locale") or {}).get("timezone") or tu.DEFAULT_TZ)
    try:
        fmt, workouts = rows_to_workouts(Path(a.csv).read_text(encoding="utf-8"), tz, a.unit)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 1
    lib = load_exercise_library()["exercises"] + data["strength"].get("exercises", [])
    names = {norm(x["name"]): x["id"] for x in lib}
    names.update({norm(x["id"]): x["id"] for x in lib})
    if a.map:
        names.update({norm(k): v for k, v in json.loads(Path(a.map).read_text()).items()})
    known_ids = {x["id"] for x in lib}
    existing = {s["id"] for s in data["strength"].get("sessions", [])}
    store = Store(ddir, actor="import")
    summary = {"status": "applied", "format": fmt, "workouts": len(workouts), "imported": 0, "already_imported": 0, "skipped_exercises": {}}
    if not a.dry_run:
        store.begin_group("strength-import")
    for w in workouts:
        sid = "imp-" + hashlib.sha256(f"{fmt}|{w['start'].isoformat()}|{w['name']}".encode()).hexdigest()[:16]
        if sid in existing:
            summary["already_imported"] += 1
            continue
        exs = []
        for name, sets in w["exercises"].items():
            eid = names.get(norm(name))
            if not eid or eid not in known_ids:
                summary["skipped_exercises"][name] = summary["skipped_exercises"].get(name, 0) + len(sets)
                continue
            exs.append({"exercise_id": eid, "sets": sets})
        if not exs:
            continue
        rec = {"id": sid, "start": w["start"].isoformat(), "name": w["name"], "source": {"hevy": "Hevy", "strong": "Strong"}.get(fmt, "CSV import"), "exercises": exs}
        if not a.dry_run:
            try:
                store.create("strength.sessions", rec)
            except EntryError as exc:
                print(json.dumps({"status": "rejected", "error": exc.message, "details": exc.details, "session": rec["start"]}))
                return 1
        summary["imported"] += 1
    summary["dry_run"] = a.dry_run
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 2 if summary["skipped_exercises"] else 0


if __name__ == "__main__":
    sys.exit(main())
