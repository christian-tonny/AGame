"""Deterministic build: validate -> migrate -> compute once -> render -> stage -> swap.

Outputs (dist/):
  fitness_dashboard.html   self-contained dashboard (inline CSS/JS/data)
  manifest.webmanifest, fitness_sw.js, icons/   PWA assets
  build_report.json        machine-readable status for the agent
  morning_summary.json     compact numbers for the morning message
  weekly_review.json       weekly aggregates (agame.weekly_review.v1)
  widgets.json             compact widget payload (agame.widgets.v1)
  snapshots/<date>.html    last N successful builds (rollback)
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from agame import SCHEMA_VERSION, __version__
from agame import timeutil as tu
from agame.compute import memo
from agame.jsonio import atomic_write_text, canonical_dumps
from agame.paths import DATA_FILES
from agame.pwa import write_assets
from agame.render import render_html
from agame.snapshot import build_snapshot
from agame.validate import validate_data

EXIT_OK, EXIT_FAILED, EXIT_DEGRADED = 0, 1, 2
KEEP_SNAPSHOTS = 7


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def input_hashes(data_dir):
    out = {}
    for f in DATA_FILES:
        p = Path(data_dir) / f
        out[f] = _sha(p.read_bytes())[:16] if p.exists() else None
    return out


def morning_summary(snap):
    """What the agent tells the owner each morning. Sentences come from compute/wording.py, the same ones the app shows."""
    from agame.compute import wording
    t = snap["today"]
    ds = snap["meta"]["data_status"]
    pick = lambda v: {"v": v.get("v"), "status": v.get("status"), "as_of": v.get("as_of")} if isinstance(v, dict) else None
    asleep = (snap["sleep"].get("last_night") or {}).get("asleep_min") if not snap["sleep"].get("stale") else None
    suggestion = next(({k: a[k] for k in ("title", "sub", "sentence", "session_id", "rule")} for a in t["adaptations"]), None)
    return {
        "contract": "agame.morning_summary.v2", "date": snap["meta"]["build_date"], "data_status": ds["overall"],
        "last_sync": ds["last_sync"], "sleep_missing": ds["sleep_missing"],
        "message": wording.morning_message(t["rings"], asleep, ds["sleep_missing"], t["coach_line"], suggestion),
        "coach_line": t["coach_line"], "suggestion": suggestion, "call": t["recommendation"]["call"],
        "action": {"id": t["action"]["id"], "text": t["action"]["text"], "kind": t["action"]["kind"]} if t.get("action") else None,
        "recovery": pick(t["rings"]["recovery"]), "sleep": pick(t["rings"]["sleep"]), "strain_yesterday": t["rings"]["strain"].get("yesterday") if t["rings"]["strain"] else None,
        "sleep_asleep_min": asleep,
        "plan": [{"title": s.get("title"), "type": s["type"], "duration_s": s.get("duration_s"), "duration": wording.hm(s.get("duration_s"))} for s in t["plan"]],
        "goals": [{"title": g["title"], "status": g.get("status_label"), "progress_pct": g.get("progress_pct")} for g in t["goals"]],
        "big_day": [{"title": b["title"], "when": b["when"]} for b in t["big_day"]],
        "fixture": snap["meta"]["fixture"],
    }


def _degraded_reasons(snap):
    ds = snap["meta"]["data_status"]
    reasons = []
    if snap["meta"]["fixture"] == "empty":
        reasons.append("empty fixtures: no real data in AGAME_DATA_DIR")
    if not ds["synced_today"]:
        reasons.append(f"no sync for {snap['meta']['build_date']} (last sync {ds['last_sync'] or 'never'})")
    if ds["sleep_missing"]:
        reasons.append("last night's sleep not synced yet")
    for dom in ("metrics", "sleep", "workouts"):
        st = ds["domains"].get(dom, {}).get("status")
        if st in ("missing", "stale") and snap["meta"]["fixture"] != "empty" and not (dom == "sleep" and ds["sleep_missing"]):
            reasons.append(f"{dom}: {st}")
    return reasons


def _next_step(report):
    """What the agent does next: the first real error and how to recover, or nothing when the build is fine."""
    errs = [e for e in report.get("errors") or [] if e.get("severity", "error") == "error"]
    if errs:
        e = errs[0]
        where = f"{e.get('file') or 'data'}{e.get('pointer') or ''}"
        return f"{where}: {e.get('message')}. Fix the batch and re-import."
    if report.get("status") == "degraded":
        return "Built with partial data. Re-import when the phone has synced: " + "; ".join(report.get("degraded_reasons") or [])
    return None


def _write_report(dist, report):
    report["next"] = _next_step(report)
    dist.mkdir(parents=True, exist_ok=True)
    atomic_write_text(dist / "build_report.json", json.dumps(report, indent=1, sort_keys=True) + "\n")


def build(data_dir, dist, build_date):
    dist = Path(dist)
    data_dir = Path(data_dir)
    report = {
        "contract": "agame.build_report.v1", "app_version": __version__, "schema_version": SCHEMA_VERSION,
        "build_date": build_date.isoformat(), "data_dir_hashes": input_hashes(data_dir) if data_dir.is_dir() else {},
        "status": "failed", "exit_code": EXIT_FAILED, "errors": [], "warnings": [], "degraded_reasons": [],
        "outputs": {}, "next": None,
    }
    if not data_dir.is_dir():
        report["errors"].append({"file": "", "pointer": "/", "message": f"data directory not found: {data_dir}"})
        _write_report(dist, report)
        return report
    memo.load(dist / ".cache" / "memo.json")
    rep, data = validate_data(data_dir, build_date)
    report["warnings"] = rep.warnings
    if not rep.ok:
        report["errors"] = rep.errors
        _write_report(dist, report)
        return report
    try:
        snap, ctx = build_snapshot(data, build_date)
        html = render_html(snap)
    except Exception as exc:  # fail loudly, keep previous dist/
        import traceback
        report["errors"].append({"file": "", "pointer": "/", "message": f"compute/render failed: {type(exc).__name__}: {exc}",
                                 "trace": traceback.format_exc().splitlines()[-6:]})
        _write_report(dist, report)
        return report
    html_b = html.encode("utf-8")
    out_hash = _sha(html_b)
    reasons = _degraded_reasons(snap)
    dist.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=str(dist)))
    try:
        (staging / "fitness_dashboard.html").write_bytes(html_b)
        pwa = write_assets(staging, snap, out_hash[:16], icon_cache=dist / ".cache" / "icons")
        extras = {
            "morning_summary.json": morning_summary(snap),
            "weekly_review.json": snap["weekly_review"],
            "widgets.json": snap["widgets"],
        }
        for name, obj in extras.items():
            (staging / name).write_text(canonical_dumps(obj, indent=1) + "\n", encoding="utf-8")
        # swap: move each staged file into place atomically
        outputs = {}
        for p in sorted(staging.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(staging)
            target = dist / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            outputs[str(rel)] = _sha(p.read_bytes())[:16]
            os.replace(p, target)
        snaps = dist / "snapshots"
        snaps.mkdir(exist_ok=True)
        shutil.copyfile(dist / "fitness_dashboard.html", snaps / f"{build_date.isoformat()}.html")
        for old in sorted(snaps.glob("*.html"))[:-KEEP_SNAPSHOTS]:
            old.unlink()
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    report.update({
        "status": "degraded" if reasons else "ok", "exit_code": EXIT_DEGRADED if reasons else EXIT_OK,
        "degraded_reasons": reasons, "output_hash": out_hash[:16], "outputs": outputs,
        "html_bytes": len(html_b), "fixture": snap["meta"]["fixture"],
        "freshness": {k: {"status": v["status"], "as_of": v["as_of"], "received": v["received"]} for k, v in snap["meta"]["data_status"]["domains"].items()},
        "data_status": snap["meta"]["data_status"]["overall"],
        "counts": {"workouts": len(snap["activities"]["list"]), "sleep_nights": len(snap["sleep"]["history"]),
                   "metrics_series": len(snap["body"]["metrics"]), "goals": len(snap["goals"])},
        "metrics_registry_size": len(snap["meta"]["metrics_registry"]),
    })
    memo.save(dist / ".cache" / "memo.json")
    _write_report(dist, report)
    return report
