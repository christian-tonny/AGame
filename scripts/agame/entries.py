"""User-entered records: create / update / delete with append-only edit history and undo.

HealthKit imports are read-only: anything not marked kind=user_entered (or a manual body
measurement) is refused with EntryError(409). Every change is validated against the same
schemas and semantic checks the build uses before it is written atomically.
"""

import copy
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from agame.datastore import load_all
from agame.jsonio import atomic_write_text, canonical_dumps
from agame.jsonschema_lite import Validator
from agame.validate import Report, _schemas, semantic_checks

# collection -> (file domain, list key, id field, editable-flag rule)
COLLECTIONS = {
    "goals.goals": ("goals", "goals", "id"),
    "nutrition.meals": ("nutrition", "meals", "id"),
    "nutrition.recipes": ("nutrition", "recipes", "id"),
    "nutrition.planned_meals": ("nutrition", "planned_meals", "id"),
    "nutrition.water": ("nutrition", "water", "source_id"),
    "nutrition.caffeine": ("nutrition", "caffeine", "source_id"),
    "plans.sessions": ("plans", "sessions", "id"),
    "plans.templates": ("plans", "templates", "id"),
    "plans.races": ("plans", "races", "id"),
    "plans.calendar": ("plans", "calendar", "id"),
    "plans.routines": ("plans", "routines", "id"),
    "plans.prehab": ("plans", "prehab", "id"),
    "plans.prehab_log": ("plans", "prehab_log", "id"),
    "journal.entries": ("journal", "entries", "id"),
    "journal.activity_status": ("journal", "activity_status", "id"),
    "journal.habits": ("journal", "habits", "id"),
    "strength.sessions": ("strength", "sessions", "id"),
    "strength.exercises": ("strength", "exercises", "id"),
    "strength.routines": ("strength", "routines", "id"),
    "load.annotations": ("load", "annotations", "id"),
    "body.measurements": ("body", "measurements", "source_id"),
    "health_records.records": ("health_records", "records", "id"),
    "coach.memory": ("coach", "memory", "id"),
    "coach.checkins": ("coach", "checkins", "id"),
}
# collections whose records carry a 'kind' field set to user_entered on create
KIND_COLLECTIONS = {"goals.goals", "nutrition.meals", "nutrition.water", "nutrition.caffeine", "plans.sessions", "journal.entries",
                    "strength.sessions", "body.measurements", "health_records.records"}
TS_FIELDS = {"load.annotations": ("created_at", "updated_at"), "coach.memory": ("created_at", "updated_at")}
PROFILE_PATCHABLE = {"targets", "ui", "coach", "smart_alarm", "beacon", "privacy", "modules", "zones", "schedule", "physiology",
                     "integrations", "auto_accept_thresholds", "athlete", "locale"}
HISTORY_FILE = "edit_history.jsonl"


class EntryError(Exception):
    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or []


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fname(domain):
    return "routes.geojson" if domain == "routes" else f"{domain}.json"


class Store:
    def __init__(self, data_dir, actor="owner"):
        self.dir = Path(data_dir)
        self.actor = actor

    # ------------------------------------------------------------------ io
    def _load(self):
        data, problems, _ = load_all(self.dir)
        if problems:
            raise EntryError(500, "data directory unreadable", problems)
        return data

    def _validate_and_write(self, data, domain):
        rep = Report()
        for e in Validator(_schemas()[domain]).validate(data[domain]):
            rep.err(_fname(domain), e.pointer, e.message)
        if rep.ok:
            semantic_checks(data, rep, None)
        errs = [e for e in rep.errors if e["file"] == _fname(domain)] or rep.errors
        if errs:
            raise EntryError(400, "change rejected by validation", errs[:20])
        p = data[domain]
        if p.get("fixture") == "empty":
            p["fixture"] = False
        p["status"] = "ok"
        p["generated_at"] = _now()
        p["source"] = p.get("source") or "user"
        atomic_write_text(self.dir / _fname(domain), canonical_dumps(p, ndigits=6, indent=1) + "\n")

    def _log(self, entry):
        entry = dict(entry, id=secrets.token_hex(8), ts=_now(), actor=self.actor)
        with open(self.dir / HISTORY_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def history(self, limit=50):
        p = self.dir / HISTORY_FILE
        if not p.exists():
            return []
        lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        return lines[-limit:][::-1]

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _spec(collection):
        if collection not in COLLECTIONS:
            raise EntryError(404, f"unknown or read-only collection '{collection}'")
        return COLLECTIONS[collection]

    @staticmethod
    def _editable(collection, rec):
        if collection == "body.measurements":
            return rec.get("kind") == "user_entered"
        if collection in KIND_COLLECTIONS and rec.get("kind") not in (None, "user_entered"):
            return False
        if rec.get("source_id") and collection in ("nutrition.meals",) and rec.get("kind") != "user_entered":
            return False
        return True

    def _find(self, items, idf, rid):
        for i, r in enumerate(items):
            if r.get(idf) == rid:
                return i
        return None

    # ------------------------------------------------------------------ operations
    def create(self, collection, record, _log=True):
        domain, key, idf = self._spec(collection)
        if not isinstance(record, dict):
            raise EntryError(400, "record must be an object")
        data = self._load()
        items = data[domain].setdefault(key, [])
        rec = copy.deepcopy(record)
        if collection == "load.annotations":
            # one annotation per workout: upsert
            idx = next((i for i, a in enumerate(items) if a["workout_id"] == rec.get("workout_id")), None)
            if idx is not None:
                return self.update(collection, items[idx]["id"], rec)
        if not rec.get(idf):
            rec[idf] = ("manual-" if idf == "source_id" else "") + secrets.token_hex(6)
        if self._find(items, idf, rec[idf]) is not None:
            raise EntryError(409, f"{idf} {rec[idf]!r} already exists")
        if collection in KIND_COLLECTIONS:
            rec["kind"] = "user_entered"
        for f in TS_FIELDS.get(collection, ()):
            rec.setdefault(f, _now())
        if collection == "strength.sessions":
            rec.setdefault("exercises", [])
            rec.setdefault("source", "manual")
        if collection == "goals.goals":
            rec.setdefault("status", "active")
            rec.setdefault("created_at", _now())
        items.append(rec)
        self._validate_and_write(data, domain)
        if _log:
            self._log({"op": "create", "domain": domain, "collection": collection, "record_id": rec[idf], "before": None, "after": rec})
        return rec

    def update(self, collection, rid, patch, _log=True):
        domain, key, idf = self._spec(collection)
        data = self._load()
        items = data[domain].setdefault(key, [])
        idx = self._find(items, idf, rid)
        if idx is None:
            raise EntryError(404, f"{collection} {rid!r} not found")
        before = copy.deepcopy(items[idx])
        if not self._editable(collection, before):
            raise EntryError(409, "imported HealthKit records are read-only; add a user_entered record instead")
        after = dict(before)
        for k, v in (patch or {}).items():
            if k in (idf, "kind"):
                continue
            after[k] = v
        if "updated_at" in TS_FIELDS.get(collection, ()):
            after["updated_at"] = _now()
        items[idx] = after
        self._validate_and_write(data, domain)
        if _log:
            self._log({"op": "update", "domain": domain, "collection": collection, "record_id": rid, "before": before, "after": after})
        return after

    def delete(self, collection, rid, _log=True):
        domain, key, idf = self._spec(collection)
        data = self._load()
        items = data[domain].setdefault(key, [])
        idx = self._find(items, idf, rid)
        if idx is None:
            raise EntryError(404, f"{collection} {rid!r} not found")
        before = items[idx]
        if not self._editable(collection, before):
            raise EntryError(409, "imported HealthKit records are read-only")
        items.pop(idx)
        self._validate_and_write(data, domain)
        if _log:
            self._log({"op": "delete", "domain": domain, "collection": collection, "record_id": rid, "before": before, "after": None})
        return before

    def patch_profile(self, patch):
        data = self._load()
        before = copy.deepcopy(data["profile"])
        for k, v in (patch or {}).items():
            if k not in PROFILE_PATCHABLE:
                raise EntryError(400, f"profile field '{k}' is not editable")
            if isinstance(v, dict) and isinstance(data["profile"].get(k), dict):
                data["profile"][k] = {**data["profile"][k], **v}
            else:
                data["profile"][k] = v
        self._validate_and_write(data, "profile")
        self._log({"op": "update", "domain": "profile", "collection": "profile", "record_id": "profile", "before": before, "after": data["profile"]})
        return data["profile"]

    def undo(self):
        """Revert the most recent change that has not been undone. Logged as op=undo."""
        hist = self.history(limit=100000)  # newest first
        undone = {h.get("undoes") for h in hist if h.get("op") == "undo"}
        target = next((h for h in hist if h.get("op") in ("create", "update", "delete") and h["id"] not in undone), None)
        if not target:
            raise EntryError(404, "nothing to undo")
        col, rid = target["collection"], target["record_id"]
        if col == "profile":
            data = self._load()
            data["profile"] = target["before"]
            self._validate_and_write(data, "profile")
        elif target["op"] == "create":
            self.delete(col, rid, _log=False)
        elif target["op"] == "delete":
            domain, key, idf = self._spec(col)
            data = self._load()
            data[domain].setdefault(key, []).append(target["before"])
            self._validate_and_write(data, domain)
        else:
            domain, key, idf = self._spec(col)
            data = self._load()
            items = data[domain][key]
            idx = self._find(items, idf, rid)
            if idx is None:
                items.append(target["before"])
            else:
                items[idx] = target["before"]
            self._validate_and_write(data, domain)
        return self._log({"op": "undo", "undoes": target["id"], "domain": target["domain"], "collection": col, "record_id": rid,
                          "before": target["after"], "after": target["before"]})

    def export(self):
        data = self._load()
        out = {"contract": "agame.export.v1", "exported_at": _now(), "collections": {}, "profile": data["profile"], "history": self.history(100000)[::-1]}
        for col, (domain, key, idf) in COLLECTIONS.items():
            rows = [r for r in data[domain].get(key, []) if self._editable(col, r)]
            if rows:
                out["collections"][col] = rows
        return out

    def delete_all_user_entered(self, confirm):
        if confirm != "DELETE-MY-ENTRIES":
            raise EntryError(400, "confirmation token required: DELETE-MY-ENTRIES")
        n = 0
        for col in COLLECTIONS:
            domain, key, idf = COLLECTIONS[col]
            data = self._load()
            items = data[domain].get(key, [])
            keep = [r for r in items if not self._editable(col, r)]
            removed = [r for r in items if self._editable(col, r)]
            if removed:
                data[domain][key] = keep
                self._validate_and_write(data, domain)
                for r in removed:
                    self._log({"op": "delete", "domain": domain, "collection": col, "record_id": r.get(idf), "before": r, "after": None})
                n += len(removed)
        return n
