#!/usr/bin/env python3
"""Rehearse the agent's mornings over HTTP only, exactly as docs/agents.md describes. No shell access to the data folder.

A dev server runs on a fresh install (empty fixtures plus the owner's own settings). The "phone" is synthetic data,
read through Muse's query shape (muse.v1). Every call carries the agent token.

  06:15 on 2 Oct  first run: history since 24 Sept, last night still syncing        -> imported, sleep marked not synced
  08:00 on 2 Oct  retry: same 3 days, sync complete                                  -> values updated, nothing duplicated
  08:00 again     identical re-send                                                  -> already_imported
  06:15 on 3 Oct  a batch with broken records                                        -> 200, the rest applied, rejected listed
  06:20 on 3 Oct  the broken records fixed and re-sent once                          -> applied
  through the day two coffees and a mood (one retried with the same Idempotency-Key), check-ins read

  python3 scripts/e2e/agent_dry_run.py [--keep DIR]
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from agame import timeutil as tu  # noqa: E402
from agame.synthetic import write_synthetic  # noqa: E402

TZ = "Africa/Kigali"
TOKEN = "dry-run-agent-token"
USER_FILES = ("profile.json", "goals.json", "plans.json", "strength.json", "journal.json", "load.json", "social.json",
              "health_records.json", "coach.json")
DAILY = {"hrv_sdnn_ms": ("heart_rate_variability_ms", "mean", 1), "resting_hr_bpm": ("resting_hr_average_bpm", "mean", 1),
         "respiratory_rate_brpm": ("respiratory_rate_average", "mean", 1), "spo2_pct": ("oxygen_saturation_average", "mean", 0.01),
         "steps": ("step_count", "sum", 1), "active_energy_kcal": ("active_energy_burned_kcal", "sum", 1),
         "vo2max_ml_kg_min": ("vo2_max", "mean", 1)}
SPORT = {"run": "running", "trail_run": "running", "walk": "walking", "ride": "cycling", "strength": "traditional_strength_training"}


def wall(iso):
    return tu.parse_ts(iso).astimezone(tu.tzinfo(TZ)).strftime("%Y-%m-%d %H:%M:%S")


class Phone:
    """Synthetic HealthKit read the way Muse's queries return it."""

    def __init__(self, src):
        self.src = src
        self.metrics = json.loads((src / "metrics.json").read_text())["series"]
        self.nights = json.loads((src / "sleep.json").read_text())["nights"]
        self.workouts = json.loads((src / "workouts.json").read_text())["workouts"]

    def daily_rows(self, days):
        rows = defaultdict(dict)
        for sid, (field, agg, k) in DAILY.items():
            per = defaultdict(list)
            for p in self.metrics.get(sid, []):
                d = p.get("date") or tu.parse_ts(p["t"]).astimezone(tu.tzinfo(TZ)).date().isoformat()
                if d in days:
                    per[d].append(p["v"])
            for d, vs in per.items():
                rows[d][field] = (sum(vs) / len(vs) if agg == "mean" else sum(vs)) * k
        return [dict(date=d, record_count=7, **r) for d, r in sorted(rows.items())]

    def sleep(self, days):
        out = []
        for n in self.nights:
            if n["date"] not in days or n.get("is_nap"):
                continue
            secs = defaultdict(float)
            for s in n["segments"]:
                secs[s["stage"]] += (tu.parse_ts(s["end"]) - tu.parse_ts(s["start"])).total_seconds()
            rec = {"id": "healthkit_" + n["source_id"], "start_datetime": wall(n["start"]), "end_datetime": wall(n["end"]), "timezone": TZ,
                   "number_of_awakenings": float(sum(1 for s in n["segments"] if s["stage"] == "awake"))}
            for st, key in (("awake", "sleep_awake_duration_sec"), ("core", "sleep_core_duration_sec"), ("deep", "sleep_deep_duration_sec"),
                            ("rem", "sleep_rem_duration_sec"), ("in_bed", "sleep_in_bed_duration_sec")):
                if st in secs:
                    rec[key] = secs[st]
            out.append(rec)
        return out

    def workout_records(self, days):
        out = []
        for w in self.workouts:
            if tu.parse_ts(w["start"]).astimezone(tu.tzinfo(TZ)).date().isoformat() not in days:
                continue
            rec = {"id": "healthkit_" + w["source_id"], "start_datetime": wall(w["start"]), "end_datetime": wall(w["end"]), "timezone": TZ,
                   "workout_type": SPORT.get(w["sport"], "other"), "is_indoor": "false"}
            for k, f in (("distance_m", "distance_meters"), ("avg_hr", "hr_average_bpm"), ("max_hr", "hr_max_bpm"), ("active_kcal", "energy_burned_kcal")):
                if w.get(k) is not None:
                    rec[f] = float(w[k])
            out.append(rec)
        return out

    def envelope(self, at, days, sleep_complete=True):
        days = set(days)
        cov = lambda complete: {"complete": complete, "interval_minutes": 30, "warning": None if complete else "Health data not synced from the device"}
        return {"format": "muse.v1", "generated_at": at, "timezone": TZ,
                "sleep": {"coverage": cov(sleep_complete), "records": self.sleep(days)},
                "workouts": {"coverage": cov(True), "records": self.workout_records(days)},
                "daily_metrics": {"coverage": cov(sleep_complete), "records": self.daily_rows(days)}}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    def __init__(self, data, dist, today):
        self.port = free_port()
        env = dict(os.environ, AGAME_QUIET="1", AGAME_DEV_TODAY=today, AGAME_AGENT_TOKEN=TOKEN)
        self.p = subprocess.Popen([sys.executable, "fitness_server.py", "--dev", "--port", str(self.port), "--data-dir", str(data), "--dist-dir", str(dist)],
                                  cwd=SCRIPTS, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/healthz", timeout=1)
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def call(self, method, path, body=None, token=TOKEN, headers=None):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def stop(self):
        self.p.terminate()
        self.p.wait(10)


def days_before(d, n):
    end = tu.parse_date(d)
    from datetime import timedelta
    return [(end - timedelta(days=k)).isoformat() for k in range(n - 1, -1, -1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep")
    a = ap.parse_args()
    work = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="agent-dry-run-"))
    if work.exists() and a.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    phone = Phone(write_synthetic(work / "phone", date(2026, 10, 4)) or work / "phone")
    data, dist = work / "agame-data", work / "dist"
    shutil.copytree(ROOT / "data", data)
    for f in USER_FILES:
        obj = json.loads((phone.src / f).read_text())
        obj["generated_at"] = obj["as_of"] = "2026-09-01T20:00:00+02:00"
        (data / f).write_text(json.dumps(obj))
    log, problems = [], []

    def expect(step, cond, what):
        if not cond:
            problems.append(f"{step}: {what}")

    def nights():
        return json.loads((data / "sleep.json").read_text())["nights"]

    # ---- 2 Oct
    srv = Server(data, dist, "2026-10-02")
    try:
        st, b = srv.call("GET", "/api/agent/morning-summary", token="wrong")
        expect("auth", st == 401, f"wrong token should be 401, got {st}")
        history = days_before("2026-10-02", 9)  # Muse's history starts on 24 Sept
        st, b = srv.call("POST", "/api/import", phone.envelope("2026-10-02T06:15:00+02:00", history, sleep_complete=False))
        log.append({"step": "06:15 first run", "http": st, "status": b.get("status"), "rejected": len(b.get("rejected", [])),
                    "build": b.get("build_report", {}).get("status"), "message": (b.get("morning_summary") or {}).get("message")})
        expect("06:15", st == 200 and b["exit_code"] in (0, 2), f"import failed: {st} {b.get('error') or b.get('status')}")
        expect("06:15", (b.get("morning_summary") or {}).get("sleep_missing") is True, "sleep should be marked not synced")
        expect("06:15", any("hasn't synced" in m for m in (b.get("morning_summary") or {}).get("message", [])), "summary should say sleep hasn't synced")
        n1 = len(nights())
        st, b = srv.call("POST", "/api/import", phone.envelope("2026-10-02T08:00:00+02:00", days_before("2026-10-02", 3)))
        log.append({"step": "08:00 retry", "http": st, "status": b.get("status"), "updated": b.get("import", {}).get("updated"),
                    "build": b.get("build_report", {}).get("status"), "message": (b.get("morning_summary") or {}).get("message")})
        expect("08:00", st == 200 and (b.get("morning_summary") or {}).get("sleep_missing") is False, "sleep should now be synced")
        expect("08:00", len(nights()) == n1, f"re-send duplicated nights ({n1} -> {len(nights())})")
        before = (data / "metrics.json").read_bytes()
        st, b = srv.call("POST", "/api/import", phone.envelope("2026-10-02T08:00:00+02:00", days_before("2026-10-02", 3)))
        log.append({"step": "08:00 identical", "http": st, "status": b.get("import", {}).get("status")})
        expect("08:00 identical", b.get("import", {}).get("status") == "already_imported" and (data / "metrics.json").read_bytes() == before, "identical re-send changed data")
    finally:
        srv.stop()

    # ---- 3 Oct
    srv = Server(data, dist, "2026-10-03")
    try:
        env = phone.envelope("2026-10-03T06:15:00+02:00", days_before("2026-10-03", 3))
        good = json.loads(json.dumps(env))
        bad_night = dict(env["sleep"]["records"][-1], id="healthkit_BROKEN", start_datetime="2026-10-03 07:00:00", end_datetime="2026-10-03 06:00:00")
        env["sleep"]["records"].append(bad_night)
        env["daily_metrics"]["records"][-1]["oxygen_saturation_average"] = 97.0  # percent instead of a 0-1 fraction
        st, b = srv.call("POST", "/api/import", env)
        rej = b.get("rejected", [])
        log.append({"step": "06:15 broken records", "http": st, "exit_code": b.get("exit_code"), "rejected": [(r.get("source_id"), r.get("field"), r["reason"]) for r in rej]})
        expect("broken", st == 200 and b.get("exit_code") == 2, f"expected 200 / exit 2, got {st} / {b.get('exit_code')}")
        expect("broken", {r.get("source_id") for r in rej} >= {"healthkit_BROKEN"} and any(r.get("field") == "oxygen_saturation_average" for r in rej), "rejected list incomplete")
        st, b = srv.call("POST", "/api/import", dict(good, generated_at="2026-10-03T06:20:00+02:00"))
        log.append({"step": "06:20 fixed re-send", "http": st, "status": b.get("status"), "rejected": len(b.get("rejected", [])),
                    "message": (b.get("morning_summary") or {}).get("message")})
        expect("fixed", st == 200 and not b.get("rejected"), "fixed batch should apply cleanly")
        coffee = {"t": "2026-10-03T08:30:00+02:00", "mg": 95}
        s1, c1 = srv.call("POST", "/api/entries/nutrition.caffeine", coffee, headers={"Idempotency-Key": "coffee-0830"})
        s2, c2 = srv.call("POST", "/api/entries/nutrition.caffeine", coffee, headers={"Idempotency-Key": "coffee-0830"})  # network retry
        s3, _ = srv.call("POST", "/api/entries/nutrition.caffeine", dict(coffee, t="2026-10-03T11:00:00+02:00"), headers={"Idempotency-Key": "coffee-1100"})
        s4, _ = srv.call("POST", "/api/entries/journal.entries", {"date": "2026-10-03", "type": "mood", "value": 2, "text": "feeling flat"}, headers={"Idempotency-Key": "mood-1"})
        s5, ck = srv.call("GET", "/api/agent/checkins?now=2026-10-03T06:00:00%2B02:00&window_min=15")
        s6, _ = srv.call("DELETE", "/api/entries/nutrition.caffeine/x")
        caffeine = [c for c in json.loads((data / "nutrition.json").read_text())["caffeine"] if c.get("kind") == "user_entered" and c["t"].startswith("2026-10-03")]
        hist = [json.loads(x) for x in (data / "edit_history.jsonl").read_text().splitlines()]
        log.append({"step": "through the day", "coffee": [s1, s2, s3], "retry_duplicate": c2.get("duplicate"), "mood": s4,
                    "checkins_due": [c["type"] for c in ck.get("due", [])], "next": [(c["type"], c["next_at"]) for c in ck.get("schedule", [])][:3],
                    "delete_refused": s6, "agent_history_entries": sum(1 for h in hist if h.get("source") == "agent")})
        expect("logging", (s1, s2, s3, s4, s5) == (200, 200, 200, 200, 200) and c2.get("duplicate") and len(caffeine) == 2, "two coffees and a mood should be logged once each")
        expect("logging", s6 == 403, "agent delete should be refused")
        expect("checkins", ck.get("schedule"), "check-in schedule missing")
    finally:
        srv.stop()

    print(json.dumps({"workdir": str(work), "steps": log, "problems": problems, "ok": not problems}, indent=1, default=str))
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
