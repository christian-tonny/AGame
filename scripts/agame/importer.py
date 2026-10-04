"""Idempotent merge of a HealthKit batch (from the agent or an Apple Health export) into the data directory.

Batch format: schemas/healthkit_batch.schema.json and docs/agents.md. Key rules:
- Every record carries a source_id. Known source_id + identical content -> skipped.
- Known source_id + different content -> updated when this batch's generated_at is newer than the stored copy,
  logged in edit_history.jsonl with before/after. User-entered records are never touched.
- A record that is the same thing under another id (same night, same workout, same daily value) is not added twice.
  A detailed record (sleep stages over time, workout samples) replaces a summary of the same thing, never the reverse.
- Timestamps without an offset are placed in the batch's "timezone"; DST-ambiguous wall times are refused.
- Idempotency key = date + hash of the batch content. Re-sending an identical batch is a no-op.
- strict (CLI default): any bad record rejects the whole batch. lenient (HTTP import): bad records are listed in
  "rejected" and the rest is applied. Either way the merged result is validated before anything is written.
"""

import copy
import hashlib
import json
import secrets
from datetime import datetime, timezone
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
HISTORY_FILE = "edit_history.jsonl"
NUTRITION_LISTS = (("meals", "id"), ("water", "source_id"), ("caffeine", "source_id"), ("daily_totals", "source_id"))
SAME_THING_OVERLAP = 0.5


class BatchError(Exception):
    pass


def _canon(x):
    return canonical_dumps(x, ndigits=6)


def _content(r):
    return _canon({k: v for k, v in r.items() if k != "synced_at"}) if isinstance(r, dict) else _canon(r)


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
    for fld in ("water", "caffeine", "daily_totals"):
        ids += [f"nutrition:{fld}:{m.get('source_id')}" for m in nut.get(fld) or []]
    ids += [f"routes:{f.get('properties', {}).get('id')}" for f in s.get("routes") or []]
    return sorted(ids)


def idempotency_key(batch):
    body = _canon({"samples": batch.get("samples") or {}, "series_meta": batch.get("series_meta") or {}, "coverage": batch.get("coverage") or {}})
    h = hashlib.sha256((batch["date"] + "\n" + body).encode()).hexdigest()[:20]
    return f"{batch['date']}:{h}"


# ---------------------------------------------------------------------------- record walking

def _records(samples):
    """Yield (label, list_owner, list_key, key_field) for every record list in a batch's samples."""
    for sid in list((samples.get("metrics") or {}).keys()):
        yield f"metrics.{sid}", samples["metrics"], sid, "source_id"
    for dom in ("sleep", "workouts", "body"):
        if samples.get(dom):
            yield dom, samples, dom, "source_id"
    nut = samples.get("nutrition") or {}
    for fld, key in NUTRITION_LISTS:
        if nut.get(fld):
            yield f"nutrition.{fld}", nut, fld, key
    if samples.get("routes"):
        yield "routes", samples, "routes", None


def _rid(r, key):
    if key is None:
        return ((r.get("properties") or {}).get("id")) if isinstance(r, dict) else None
    return r.get(key) if isinstance(r, dict) else None


def _record_problems(label, r, key):
    if not isinstance(r, dict):
        return "record must be an object"
    if key is None:
        return None if _rid(r, None) else "every route feature needs properties.id"
    if label == "nutrition.meals" and not (r.get("id") and r.get("source_id")):
        return "every meal needs an id and a source_id"
    if not r.get(key):
        return f"every record needs a {key}"
    if r.get("kind") == "user_entered":
        return "HealthKit batches cannot contain user_entered records; those are made in the app"
    return None


def _localize_record(label, r, tz):
    rtz = r.pop("timezone", None) or tz
    for f in ("t", "start", "end"):
        if f in r and r[f] is not None:
            r[f] = tu.localize(r[f], rtz)
    for seg in r.get("segments") or []:
        if label == "sleep":
            for f in ("start", "end"):
                if seg.get(f) is not None:
                    seg[f] = tu.localize(seg[f], rtz)
    for sp in r.get("splits") or []:
        for f in ("start", "end"):
            if sp.get(f) is not None:
                sp[f] = tu.localize(sp[f], rtz)


def _check_batch(batch):
    if not isinstance(batch, dict):
        raise BatchError("batch must be a JSON object")
    for k in ("batch_version", "date", "generated_at", "samples"):
        if k not in batch:
            raise BatchError(f"batch missing '{k}'")
    if batch["batch_version"] not in (1, 2):
        raise BatchError(f"unknown batch_version {batch['batch_version']!r} (this server reads 1 and 2)")
    tz = batch.get("timezone")
    if tz:
        try:
            tu.tzinfo(tz)
        except Exception:
            raise BatchError(f"unknown timezone {tz!r}")
    try:
        tu.parse_date(batch["date"])
        batch["generated_at"] = tu.localize(batch["generated_at"], tz)
    except (ValueError, TypeError) as exc:
        raise BatchError(f"bad date/generated_at: {exc}")
    if not isinstance(batch["samples"], dict):
        raise BatchError("samples must be an object")
    for sid, pts in (batch["samples"].get("metrics") or {}).items():
        if not isinstance(pts, list):
            raise BatchError(f"metrics.{sid} must be a list")


def _screen_records(batch, lenient, rejected):
    """Drop (lenient) or refuse (strict) records that are malformed before merging; localize their timestamps."""
    tz = batch.get("timezone")
    for label, owner, lkey, key in list(_records(batch["samples"])):
        keep = []
        for r in owner[lkey]:
            prob = _record_problems(label, r, key)
            if prob is None:
                try:
                    _localize_record(label, r, tz)
                except (ValueError, TypeError) as exc:
                    prob = str(exc)
            if prob is None:
                keep.append(r)
                continue
            if not lenient:
                raise BatchError(f"{label}: {prob}")
            rejected.append({"domain": label, "source_id": _rid(r, key), "reason": prob})
        owner[lkey] = keep


# ---------------------------------------------------------------------------- same-thing matching

def _span(r):
    try:
        return tu.parse_ts(r["start"]), tu.parse_ts(r["end"])
    except (KeyError, TypeError, ValueError):
        return None


def _overlap(a, b):
    sa, sb = _span(a), _span(b)
    if not sa or not sb:
        return 0.0
    inter = (min(sa[1], sb[1]) - max(sa[0], sb[0])).total_seconds()
    shorter = min((sa[1] - sa[0]).total_seconds(), (sb[1] - sb[0]).total_seconds())
    return inter / shorter if inter > 0 and shorter > 0 else 0.0


def _instant(v):
    try:
        return tu.parse_ts(v).astimezone(timezone.utc).replace(microsecond=0)
    except (TypeError, ValueError):
        return v


FAMILY = {"run": "run", "trail_run": "run", "treadmill_run": "run", "track_run": "run", "walk": "walk", "hike": "walk",
          "ride": "ride", "virtual_ride": "ride", "swim": "swim", "open_water_swim": "swim"}


def _same_thing(label, existing, r):
    if label == "sleep":
        return bool(r.get("is_nap")) == bool(existing.get("is_nap")) and _overlap(existing, r) >= SAME_THING_OVERLAP
    if label == "workouts":
        return FAMILY.get(existing.get("sport"), existing.get("sport")) == FAMILY.get(r.get("sport"), r.get("sport")) and _overlap(existing, r) >= SAME_THING_OVERLAP
    if label.startswith("metrics."):
        if "date" in r and "date" in existing:
            return r["date"] == existing["date"]
        return "t" in r and "t" in existing and _instant(r["t"]) == _instant(existing["t"])
    if label == "body":
        return r.get("type") == existing.get("type") and _instant(r.get("t")) == _instant(existing.get("t"))
    if label in ("nutrition.water", "nutrition.caffeine"):
        return _instant(r.get("t")) == _instant(existing.get("t"))
    if label == "nutrition.daily_totals":
        return r.get("date") == existing.get("date")
    return False


def _richer(label, r, existing):
    if label == "sleep":
        return bool(r.get("segments")) and not existing.get("segments")
    if label == "workouts":
        return bool(r.get("samples")) and not existing.get("samples")
    return False


def _bucket(label, r):
    """Coarse index key so same-thing matching only looks at nearby records."""
    if label.startswith("metrics.") or label == "nutrition.daily_totals":
        return r.get("date") or str(r.get("t", ""))[:10]
    for f in ("start", "t"):
        if r.get(f):
            try:
                return tu.parse_ts(r[f]).astimezone(timezone.utc).date().isoformat()
            except (TypeError, ValueError):
                return None
    return None


def _neighbours(bucket):
    if not bucket or len(bucket) != 10:
        return [bucket]
    d = tu.parse_date(bucket)
    from datetime import timedelta
    return [(d + timedelta(days=k)).isoformat() for k in (-1, 0, 1)]


# ---------------------------------------------------------------------------- merge

def _merge_list(existing, incoming, key, label, summary, gen_at, changes):
    index = {_rid(r, key): i for i, r in enumerate(existing) if _rid(r, key) is not None}
    buckets = {}
    for i, r in enumerate(existing):
        buckets.setdefault(_bucket(label, r), []).append(i)
    seen_in_batch = {}
    changed = 0
    for r in incoming:
        k = _rid(r, key)
        if k in seen_in_batch:
            if _content(seen_in_batch[k]) != _content(r):
                summary["conflicts"].append({"domain": label, "source_id": k, "reason": "two different records with the same id in this batch"})
            else:
                summary["skipped_duplicate"] += 1
            continue
        seen_in_batch[k] = r
        r = dict(r, synced_at=gen_at) if key is not None else r
        if k in index:
            cur = existing[index[k]]
            if cur.get("kind") == "user_entered":
                summary["conflicts"].append({"domain": label, "source_id": k, "reason": "a record you entered in the app has this id; it is never overwritten"})
                continue
            if _content(cur) == _content(r):
                summary["skipped_duplicate"] += 1
                continue
            if cur.get("synced_at") and tu.parse_ts(cur["synced_at"]) > tu.parse_ts(gen_at):
                summary["stale"].append({"domain": label, "source_id": k, "reason": "a newer copy is already stored"})
                continue
            existing[index[k]] = r
            changes.append({"label": label, "record_id": k, "before": cur, "after": r})
            summary["updated"][label] = summary["updated"].get(label, 0) + 1
            changed += 1
            continue
        match = None
        if key is not None:
            for b in _neighbours(_bucket(label, r)):
                for i in buckets.get(b, []):
                    if _same_thing(label, existing[i], r) and existing[i].get("kind") != "user_entered":
                        match = i
                        break
                if match is not None:
                    break
        if match is not None:
            cur = existing[match]
            if _richer(label, r, cur):
                existing[match] = r
                index.pop(_rid(cur, key), None)
                index[k] = match
                changes.append({"label": label, "record_id": k, "before": cur, "after": r, "replaces": _rid(cur, key)})
                summary["updated"][label] = summary["updated"].get(label, 0) + 1
                changed += 1
            else:
                summary["duplicates"].append({"domain": label, "source_id": k, "same_as": _rid(cur, key)})
            continue
        existing.append(r)
        index[k] = len(existing) - 1
        buckets.setdefault(_bucket(label, r), []).append(len(existing) - 1)
        summary["added"][label] = summary["added"].get(label, 0) + 1
        changed += 1
    return changed


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


def _merge(data, batch, summary, changes):
    new = copy.deepcopy(data)
    s = batch["samples"]
    touched = set()
    gen_at = batch["generated_at"]
    bdate = tu.parse_date(batch["date"])

    if s.get("metrics"):
        series = new["metrics"].setdefault("series", {})
        for sid, pts in s["metrics"].items():
            if _merge_list(series.setdefault(sid, []), pts, "source_id", f"metrics.{sid}", summary, gen_at, changes):
                touched.add("metrics")
            series[sid].sort(key=lambda p: (p.get("t") or p.get("date") or "", p["source_id"]))
        for sid, meta in (batch.get("series_meta") or {}).items():
            if new["metrics"].setdefault("series_meta", {}).get(sid) != meta:
                new["metrics"]["series_meta"][sid] = meta
                touched.add("metrics")
    for dom, lkey, sort in (("sleep", "nights", lambda n: (n["end"], n["source_id"])), ("workouts", "workouts", lambda w: (w["start"], w["source_id"])),
                            ("body", "measurements", lambda m: (m["t"], m["source_id"]))):
        if s.get(dom):
            if _merge_list(new[dom][lkey], s[dom], "source_id", dom, summary, gen_at, changes):
                touched.add(dom)
            new[dom][lkey].sort(key=sort)
    if s.get("nutrition"):
        nut = s["nutrition"]
        for fld, key_ in NUTRITION_LISTS:
            if nut.get(fld):
                if _merge_list(new["nutrition"].setdefault(fld, []), nut[fld], key_, f"nutrition.{fld}", summary, gen_at, changes):
                    touched.add("nutrition")
                new["nutrition"][fld].sort(key=lambda m: (m.get("t") or m.get("date") or "", m.get(key_) or ""))
        if "nutrition" in touched:
            new["nutrition"]["connected"] = True
    if s.get("routes"):
        if _merge_list(new["routes"]["features"], s["routes"], None, "routes", summary, gen_at, changes):
            touched.add("routes")

    # envelopes + sync manifest
    coverage = batch.get("coverage") or {}
    domains = new["current"].setdefault("domains", {})
    for dom in sorted(touched):
        p = new[dom]
        p["schema_version"] = SCHEMA_VERSION
        p["generated_at"] = gen_at
        p["source"] = batch.get("source") or "healthkit"
        if p.get("fixture") == "empty":
            p["fixture"] = False
        if dom == "metrics":
            last = _max_ts([pt.get("t") for pts in p["series"].values() for pt in pts]) or gen_at
        elif dom == "sleep":
            last = _max_ts([n["end"] for n in p["nights"]])
        elif dom == "workouts":
            last = _max_ts([w["end"] for w in p["workouts"]])
        elif dom == "body":
            last = _max_ts([m["t"] for m in p["measurements"]])
        elif dom == "nutrition":
            last = _max_ts([m["t"] for m in p.get("meals", [])]) or gen_at
        else:
            last = gen_at
        p["as_of"] = last
        p["status"] = "ok"
    for dom in ("metrics", "sleep", "workouts", "body", "nutrition"):
        cov = coverage.get(dom)
        if not (dom in touched or dom in s.keys() or cov):
            continue
        received = dom in touched
        if dom == "sleep":
            received = any(n.get("date") == batch["date"] or (tu.parse_ts(n["end"]).date() == bdate) for n in new["sleep"]["nights"])
        prev = domains.get(dom, {})
        event_based = dom in ("workouts", "body", "nutrition")  # nothing new is normal for these
        if event_based and not received:
            received = True
        if dom == "metrics" and not received and prev.get("expected_for") == batch["date"] and prev.get("received"):
            received = True  # an identical re-send of today's metrics
        incomplete = bool(cov) and cov.get("complete") is False
        if incomplete and dom == "sleep":
            received = False
        status = "ok" if received else ("partial" if dom in touched else "missing")
        if incomplete and status == "ok":
            status = "partial"
        note = ("No new samples" if dom not in touched else None) if received else ("Sleep not synced yet" if dom == "sleep" else "No new samples")
        if incomplete and dom != "sleep":
            note = "Still syncing from the phone"
        entry = {
            "last_sync": gen_at if (dom in touched or cov) else prev.get("last_sync"),
            "last_sample": new[dom].get("as_of") if dom in touched else prev.get("last_sample"),
            "expected_for": batch["date"],
            "received": bool(received),
            "status": status,
            "note": note,
        }
        if cov:
            entry["coverage"] = {"complete": cov.get("complete"), "note": cov.get("note")}
        domains[dom] = entry
    counts = {k: v for k, v in summary["added"].items() if v}
    counts.update({f"updated.{k}": v for k, v in summary["updated"].items() if v})
    new["current"].setdefault("imports", []).append({"idempotency_key": summary["idempotency_key"], "date": batch["date"], "at": gen_at, "counts": counts})
    new["current"]["imports"] = new["current"]["imports"][-60:]
    new["current"]["generated_at"] = gen_at
    new["current"]["as_of"] = gen_at
    new["current"]["status"] = "ok"
    new["current"]["source"] = batch.get("source") or "healthkit"
    if new["current"].get("fixture") == "empty":
        new["current"]["fixture"] = False
    touched.add("current")
    return new, touched


def _validate(new, touched, bdate):
    rep = Report()
    schemas = _schemas()
    for dom in touched:
        for e in Validator(schemas[dom]).validate(new[dom]):
            rep.err(DOMAIN_FILES[dom], e.pointer, e.message)
    if rep.ok:
        semantic_checks(new, rep, bdate)
    return rep


FILE_LISTS = {"sleep.json": ("sleep", "nights", "sleep"), "workouts.json": ("workouts", "workouts", "workouts"),
              "body.json": ("body", "measurements", "body"), "routes.geojson": ("routes", "features", "routes")}


def _culprit(new, err):
    """Map a validation error back to (batch label, record id), or None when it is not about one record."""
    parts = [p for p in (err.get("pointer") or "").split("/") if p]
    f = err.get("file")
    try:
        if f == "metrics.json" and len(parts) >= 3 and parts[0] == "series":
            return f"metrics.{parts[1]}", new["metrics"]["series"][parts[1]][int(parts[2])].get("source_id")
        if f == "nutrition.json" and len(parts) >= 2:
            key = dict(NUTRITION_LISTS).get(parts[0])
            if key:
                return f"nutrition.{parts[0]}", new["nutrition"][parts[0]][int(parts[1])].get(key)
        if f in FILE_LISTS and len(parts) >= 2:
            dom, lkey, label = FILE_LISTS[f]
            rec = new[dom][lkey][int(parts[1])]
            return label, _rid(rec, None if dom == "routes" else "source_id")
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    return None


def _drop(batch, label, rid):
    for lab, owner, lkey, key in _records(batch["samples"]):
        if lab == label:
            owner[lkey] = [r for r in owner[lkey] if _rid(r, key) != rid]


def _log_changes(data_dir, changes, gen_at):
    if not changes:
        return
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = []
    for c in changes:
        dom = c["label"].split(".")[0]
        lines.append(json.dumps({"id": secrets.token_hex(8), "ts": now, "op": "import_update", "actor": "importer", "source": "healthkit",
                                 "domain": dom, "collection": c["label"], "record_id": c["record_id"], "replaces": c.get("replaces"),
                                 "batch_generated_at": gen_at, "before": c["before"], "after": c["after"]}, sort_keys=True))
    with open(Path(data_dir) / HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def apply_batch(data_dir, batch, dry_run=False, lenient=False):
    """Merge batch into data_dir. Returns (summary, exit_code): 0 applied, 2 applied with something left out, 1 nothing written."""
    rejected, info = [], None
    if isinstance(batch, dict) and batch.get("format"):
        from agame import muse
        try:
            batch, rejected, info = muse.to_batch(batch)
        except muse.MuseError as exc:
            raise BatchError(str(exc))
        if rejected and not lenient:
            raise BatchError(f"{rejected[0]['domain']}: {rejected[0]['reason']}")
    batch = copy.deepcopy(batch)
    _check_batch(batch)
    _screen_records(batch, lenient, rejected)
    data, problems, _ = load_all(data_dir)
    if problems:
        raise BatchError("existing data unreadable: " + "; ".join(p["message"] for p in problems))
    key = idempotency_key(batch)
    base = {"idempotency_key": key, "date": batch["date"], "status": "applied", "dry_run": dry_run, "rejected": rejected}
    if info:
        base["adapter"] = info
    if any(imp.get("idempotency_key") == key for imp in data["current"].get("imports", [])):
        return dict(base, status="already_imported", added={}, updated={}, skipped_duplicate=0, conflicts=[], stale=[], duplicates=[], domains_touched=[]), (2 if rejected else 0)
    bdate = tu.parse_date(batch["date"])
    for _ in range(50):
        summary = dict(base, added={}, updated={}, skipped_duplicate=0, conflicts=[], stale=[], duplicates=[], domains_touched=[], rejected=list(rejected))
        changes = []
        new, touched = _merge(data, batch, summary, changes)
        rep = _validate(new, touched, bdate)
        if rep.ok:
            break
        culprits = [(_culprit(new, e), e) for e in rep.errors]
        if not lenient or any(c is None for c, _ in culprits):
            summary["status"] = "rejected"
            summary["errors"] = rep.errors[:50]
            return summary, 1
        for (label, rid), e in culprits:
            if not any(r.get("source_id") == rid and r.get("domain") == label for r in rejected):
                rejected.append({"domain": label, "source_id": rid, "reason": e["message"], "pointer": e.get("pointer")})
            _drop(batch, label, rid)
    else:
        summary["status"] = "rejected"
        summary["errors"] = rep.errors[:50]
        return summary, 1
    applied = bool(summary["added"] or summary["updated"])
    remaining = sum(len(owner[lkey]) for _, owner, lkey, _ in _records(batch["samples"]))
    if rejected and not remaining:
        summary["status"] = "rejected"
        return summary, 1
    summary["domains_touched"] = sorted(touched)
    if rejected or summary["conflicts"] or summary["stale"]:
        summary["status"] = "partial"
    if not dry_run:
        pairs = []
        for dom in sorted(touched):
            indent = None if dom in ("workouts", "metrics", "sleep", "routes") else 1
            pairs.append((Path(data_dir) / DOMAIN_FILES[dom], canonical_dumps(new[dom], ndigits=6, indent=indent) + "\n"))
        atomic_write_many(pairs)
        _log_changes(data_dir, changes, batch["generated_at"])
    return summary, (2 if (rejected or summary["conflicts"] or summary["stale"]) else 0)
