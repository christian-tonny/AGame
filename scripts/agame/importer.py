"""Idempotent merge of a HealthKit batch (produced by Steve) into the data directory.

Batch format: docs/data-contract.md §"HealthKit batch". Key rules:
- Every record carries a source_id. Known source_id + identical content -> skipped.
- Known source_id + different content -> conflict, NOT applied (imports are immutable).
- Idempotency key = date + sha256(sorted source IDs). A batch already imported is a no-op.
- All touched files are validated as a whole and written all-or-nothing.
"""

import copy
import hashlib
from pathlib import Path

from agame import SCHEMA_VERSION
from agame import timeutil as tu
from agame.datastore import load_all
from agame.jsonio import atomic_write_many, canonical_dumps
from agame.jsonschema_lite import Validator
from agame.validate import Report, _schemas, semantic_checks

DOMAIN_FILES = {
    "metrics": "metrics.json", "sleep": "sleep.json", "workouts": "workouts.json", "body": "body.json",
    "nutrition": "nutrition.json", "routes": "routes.geojson", "current": "current.json",
}


class BatchError(Exception):
    pass


def _canon(x):
    return canonical_dumps(x, ndigits=6)


def batch_source_ids(batch):
    s = batch.get("samples") or {}
    ids = []
    for sid, pts in (s.get("metrics") or {}).items():
        ids += [f"metrics:{sid}:{p.get('source_id')}" for p in pts]
    ids += [f"sleep:{n.get('source_id')}" for n in s.get("sleep") or []]
    ids += [f"workouts:{w.get('source_id')}" for w in s.get("workouts") or []]
    ids += [f"body:{m.get('source_id')}" for m in s.get("body") or []]
    nut = s.get("nutrition") or {}
    ids += [f"nutrition:meal:{m.get('source_id') or m.get('id')}" for m in nut.get("meals") or []]
    ids += [f"nutrition:water:{m.get('source_id')}" for m in nut.get("water") or []]
    ids += [f"nutrition:caffeine:{m.get('source_id')}" for m in nut.get("caffeine") or []]
    ids += [f"routes:{f.get('properties', {}).get('id')}" for f in s.get("routes") or []]
    return sorted(ids)


def idempotency_key(batch):
    h = hashlib.sha256("\n".join([batch["date"]] + batch_source_ids(batch)).encode()).hexdigest()[:20]
    return f"{batch['date']}:{h}"


def _check_batch(batch):
    if not isinstance(batch, dict):
        raise BatchError("batch must be a JSON object")
    for k in ("batch_version", "date", "generated_at", "samples"):
        if k not in batch:
            raise BatchError(f"batch missing '{k}'")
    try:
        tu.parse_date(batch["date"])
        tu.parse_ts(batch["generated_at"])
    except (ValueError, TypeError) as exc:
        raise BatchError(f"bad date/generated_at: {exc}")
    if not isinstance(batch["samples"], dict):
        raise BatchError("samples must be an object")
    for sid, pts in (batch["samples"].get("metrics") or {}).items():
        if not isinstance(pts, list):
            raise BatchError(f"metrics.{sid} must be a list")
        for p in pts:
            if not isinstance(p, dict) or not p.get("source_id"):
                raise BatchError(f"metrics.{sid}: every point needs a source_id")
    for dom, key in (("sleep", "source_id"), ("workouts", "source_id"), ("body", "source_id")):
        for r in batch["samples"].get(dom) or []:
            if not isinstance(r, dict) or not r.get(key):
                raise BatchError(f"{dom}: every record needs a {key}")
    for f in batch["samples"].get("routes") or []:
        if not (f.get("properties") or {}).get("id"):
            raise BatchError("routes: every feature needs properties.id")


def _merge_list(existing, incoming, key, label, summary):
    index = {r.get(key): i for i, r in enumerate(existing) if r.get(key) is not None}
    seen_in_batch = {}
    added = 0
    for r in incoming:
        k = r.get(key)
        if k in seen_in_batch:
            if _canon(seen_in_batch[k]) != _canon(r):
                summary["conflicts"].append({"domain": label, "source_id": k, "reason": "two different records with the same id in this batch"})
            else:
                summary["skipped_duplicate"] += 1
            continue
        seen_in_batch[k] = r
        if k in index:
            if _canon(existing[index[k]]) == _canon(r):
                summary["skipped_duplicate"] += 1
            else:
                summary["conflicts"].append({"domain": label, "source_id": k, "reason": "record already imported with different content (imports are immutable)"})
            continue
        existing.append(r)
        index[k] = len(existing) - 1
        added += 1
    summary["added"][label] = summary["added"].get(label, 0) + added
    return added


def _max_ts(values):
    out = None
    for v in values:
        if not v:
            continue
        try:
            dt = tu.parse_ts(v)
        except ValueError:
            continue
        if out is None or dt > out:
            out = dt
    return out.isoformat() if out else None


def apply_batch(data_dir, batch, dry_run=False):
    """Merge batch into data_dir. Returns (summary, exit_code)."""
    _check_batch(batch)
    data, problems, _ = load_all(data_dir)
    if problems:
        raise BatchError("existing data unreadable: " + "; ".join(p["message"] for p in problems))
    key = idempotency_key(batch)
    summary = {"idempotency_key": key, "date": batch["date"], "added": {}, "skipped_duplicate": 0, "conflicts": [],
               "domains_touched": [], "status": "applied", "dry_run": dry_run}
    if any(imp.get("idempotency_key") == key for imp in data["current"].get("imports", [])):
        summary["status"] = "already_imported"
        return summary, 0

    new = copy.deepcopy(data)
    s = batch["samples"]
    touched = set()
    gen_at = batch["generated_at"]
    bdate = tu.parse_date(batch["date"])

    if s.get("metrics"):
        series = new["metrics"].setdefault("series", {})
        for sid, pts in s["metrics"].items():
            if _merge_list(series.setdefault(sid, []), pts, "source_id", f"metrics.{sid}", summary):
                touched.add("metrics")
            series[sid].sort(key=lambda p: (p.get("t") or p.get("date") or "", p["source_id"]))
        for sid, meta in (batch.get("series_meta") or {}).items():
            new["metrics"].setdefault("series_meta", {})[sid] = meta
            touched.add("metrics")
    if s.get("sleep"):
        if _merge_list(new["sleep"]["nights"], s["sleep"], "source_id", "sleep", summary):
            touched.add("sleep")
        new["sleep"]["nights"].sort(key=lambda n: (n["end"], n["source_id"]))
    if s.get("workouts"):
        if _merge_list(new["workouts"]["workouts"], s["workouts"], "source_id", "workouts", summary):
            touched.add("workouts")
        new["workouts"]["workouts"].sort(key=lambda w: (w["start"], w["source_id"]))
    if s.get("body"):
        if _merge_list(new["body"]["measurements"], s["body"], "source_id", "body", summary):
            touched.add("body")
        new["body"]["measurements"].sort(key=lambda m: (m["t"], m["source_id"]))
    if s.get("nutrition"):
        nut = s["nutrition"]
        for fld, key_ in (("meals", "id"), ("water", "source_id"), ("caffeine", "source_id")):
            if nut.get(fld):
                if _merge_list(new["nutrition"].setdefault(fld, []), nut[fld], key_, f"nutrition.{fld}", summary):
                    touched.add("nutrition")
                new["nutrition"][fld].sort(key=lambda m: (m["t"], m.get(key_) or ""))
        if "nutrition" in touched:
            new["nutrition"]["connected"] = True
    if s.get("routes"):
        feats = new["routes"]["features"]
        index = {f["properties"]["id"]: i for i, f in enumerate(feats)}
        added = 0
        for f in s["routes"]:
            rid = f["properties"]["id"]
            if rid in index:
                if _canon(feats[index[rid]]) == _canon(f):
                    summary["skipped_duplicate"] += 1
                else:
                    summary["conflicts"].append({"domain": "routes", "source_id": rid, "reason": "route already imported with different geometry"})
                continue
            feats.append(f)
            index[rid] = len(feats) - 1
            added += 1
        summary["added"]["routes"] = added
        if added:
            touched.add("routes")

    # envelopes + sync manifest
    domains = new["current"].setdefault("domains", {})
    for dom in sorted(touched):
        p = new[dom]
        p["schema_version"] = SCHEMA_VERSION
        p["generated_at"] = gen_at
        p["source"] = batch.get("source") or "healthkit"
        if p.get("fixture") == "empty":
            p["fixture"] = False
        if dom == "metrics":
            last = _max_ts([pt.get("t") for pts in p["series"].values() for pt in pts])
        elif dom == "sleep":
            last = _max_ts([n["end"] for n in p["nights"]])
        elif dom == "workouts":
            last = _max_ts([w["end"] for w in p["workouts"]])
        elif dom == "body":
            last = _max_ts([m["t"] for m in p["measurements"]])
        elif dom == "nutrition":
            last = _max_ts([m["t"] for m in p.get("meals", [])])
        else:
            last = gen_at
        p["as_of"] = last
        p["status"] = "ok"
    for dom in ("metrics", "sleep", "workouts", "body", "nutrition"):
        if dom in touched or dom in (s.keys()):
            received = dom in touched
            if dom == "sleep":
                received = any(n.get("date") == batch["date"] or (tu.parse_ts(n["end"]).date() == bdate) for n in new["sleep"]["nights"])
            prev = domains.get(dom, {})
            domains[dom] = {
                "last_sync": gen_at if dom in touched else prev.get("last_sync"),
                "last_sample": new[dom].get("as_of") if dom in touched else prev.get("last_sample"),
                "expected_for": batch["date"],
                "received": bool(received),
                "status": "ok" if received else ("partial" if dom in touched else "missing"),
                "note": None if received else ("Sleep not synced yet" if dom == "sleep" else "No new samples"),
            }
    counts = {k: v for k, v in summary["added"].items() if v}
    new["current"].setdefault("imports", []).append({"idempotency_key": key, "date": batch["date"], "at": gen_at, "counts": counts})
    new["current"]["imports"] = new["current"]["imports"][-60:]
    new["current"]["generated_at"] = gen_at
    new["current"]["as_of"] = gen_at
    new["current"]["status"] = "ok"
    new["current"]["source"] = batch.get("source") or "healthkit"
    if new["current"].get("fixture") == "empty":
        new["current"]["fixture"] = False
    touched.add("current")

    # validate merged state before writing anything
    rep = Report()
    schemas = _schemas()
    for dom in touched:
        for e in Validator(schemas[dom]).validate(new[dom]):
            rep.err(DOMAIN_FILES[dom], e.pointer, e.message)
    if rep.ok:
        semantic_checks(new, rep, bdate)
    if not rep.ok:
        summary["status"] = "rejected"
        summary["errors"] = rep.errors[:50]
        return summary, 1
    summary["domains_touched"] = sorted(touched)
    if not dry_run:
        pairs = []
        for dom in sorted(touched):
            indent = None if dom in ("workouts", "metrics", "sleep", "routes") else 1
            pairs.append((Path(data_dir) / DOMAIN_FILES[dom], canonical_dumps(new[dom], ndigits=6, indent=indent) + "\n"))
        atomic_write_many(pairs)
    return summary, (2 if summary["conflicts"] else 0)
