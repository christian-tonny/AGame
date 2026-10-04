"""Owner actions that change several records or need server-side lookups.

The browser only names an action and the record it applies to. Everything that decides new
values (which alternative, how a template session becomes a real one, which threshold is a
valid candidate, how a meal is copied) happens here, in Python, through the same Store that
validates every write and keeps edit history. One action = one undo step (grouped history).
"""

import base64
import re
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from agame import timeutil as tu
from agame.entries import EntryError
from agame.paths import load_config

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ROUTE_TEXT = 5 * 1024 * 1024
MAX_ROUTE_POINTS = 2000
UPLOAD_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
SESSION_FIELDS = ("date", "type", "sport", "title", "duration_s", "distance_m", "priority", "guiding_metric", "steps", "objective",
                  "load_planned", "start_time", "routine_id", "template_id", "plan_id", "forecast_temp_c")


def _req(body, *keys):
    missing = [k for k in keys if body.get(k) in (None, "")]
    if missing:
        raise EntryError(400, "missing field(s): " + ", ".join(missing))
    return [body[k] for k in keys]


def _date(s, field="date"):
    try:
        return tu.parse_date(s).isoformat()
    except (TypeError, ValueError):
        raise EntryError(400, f"{field} must be YYYY-MM-DD")


class Actions:
    def __init__(self, store, snapshot, data_dir):
        self.store = store
        self.snap = snapshot
        self.data_dir = data_dir

    # ------------------------------------------------------------------ helpers
    def _raw(self):
        return self.store._load()

    def _cfg(self):
        return load_config(self._raw()["profile"])

    def _label(self, typ):
        return self._cfg()["plans"]["type_labels"].get(typ, typ)

    def _session(self, sid):
        P = self.snap["plans"]
        pools = [P["today"], P["tomorrow"], P["upcoming"], P["this_week"]["sessions"], P["next_week"]["sessions"], P["last_week"]["sessions"]]
        found = None
        for pool in pools:
            for s in pool:
                if s["id"] == sid:
                    found = dict(found or {}, **s) if found else dict(s)
        if not found:
            raise EntryError(404, f"session {sid!r} not found in the current plan")
        return found

    def _write_session(self, s, changes, note=None):
        """Update an explicit session, or turn a template-generated one into a real record (same date unless changed)."""
        if note:
            changes = dict(changes, objective=((s.get("objective") or "") + (" · " if s.get("objective") else "") + note)[:500])
        if s.get("origin") == "plan":
            return self.store.update("plans.sessions", s["id"], changes)
        rec = {k: s.get(k) for k in SESSION_FIELDS if s.get(k) is not None}
        rec.setdefault("steps", [])
        rec.update(changes)
        rec["status"] = rec.get("status") or "planned"
        return self.store.create("plans.sessions", rec)

    def _was(self, s):
        dur = f", {round(s['duration_s'] / 60)} min" if s.get("duration_s") else ""
        return f"Was: {s.get('title') or self._label(s['type'])} ({s['type']}{dur})"

    # ------------------------------------------------------------------ plans
    def plan_move(self, body):
        sid, date = _req(body, "session_id", "date")
        date = _date(date)
        s = self._session(sid)
        if s["date"] == date:
            raise EntryError(400, "session is already on that day")
        self.store.begin_group("move")
        if s.get("origin") == "plan":
            return self.store.update("plans.sessions", sid, {"date": date, "status": "planned"})
        rec = self._write_session(s, {"date": date})
        # keep the template from regenerating the session on its old day
        self.store.create("plans.sessions", {"date": s["date"], "type": "REST", "title": f"Moved to {date}", "steps": [], "status": "moved"})
        return rec

    def plan_alternative(self, body):
        sid, kind = _req(body, "session_id", "kind")
        s = self._session(sid)
        alt = next((a for a in s.get("alternatives") or [] if a["kind"] == kind), None)
        if not alt:
            raise EntryError(404, f"no {kind!r} alternative for this session")
        self.store.begin_group("wizard")
        ch = {"type": alt["type"], "title": alt["title"], "duration_s": alt["duration_s"] or None, "load_planned": alt.get("est_load")}
        if alt["type"] == "REST":
            ch.update(duration_s=None, load_planned=None)
        return self._write_session(s, ch, note=f"Workout Wizard: {alt['note']}. {self._was(s)}")

    def plan_adaptation(self, body):
        sid, rule, decision = _req(body, "session_id", "rule", "decision")
        if decision not in ("accepted", "declined"):
            raise EntryError(400, "decision must be accepted or declined")
        a = next((x for x in self.snap["plans"]["adaptations"] if x["session_id"] == sid and x["rule"] == rule), None)
        if not a:
            raise EntryError(404, "that suggestion is no longer active")
        self.store.begin_group("adapt")
        rec = None
        if decision == "accepted":
            s = self._session(sid)
            why = f"{a['reason']}. {self._was(s)}"
            if a["action"] == "swap":
                ch = {"type": a["to"], "title": self._label(a["to"])}
                if a["to"] == "REST":
                    ch.update(duration_s=None, load_planned=None)
                rec = self._write_session(s, ch, note=why)
            elif a["action"] == "shorten":
                rec = self._write_session(s, {"duration_s": round((s.get("duration_s") or 0) * a["factor"] / 60) * 60 or None}, note=why)
            elif a["action"] == "move":
                rec = self.plan_move({"session_id": sid, "date": a["to_date"]}) if s["date"] != a["to_date"] else None
            elif a["action"] == "adjust_pace":
                rec = self._write_session(s, {}, note=f"Run about {a['pct_slower']}% slower than usual targets. {a['reason']}")
        self.store.create("plans.decisions", {"session_id": sid, "rule": rule, "decision": decision, "date": a["date"],
                                              "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat()})
        return rec or {"session_id": sid, "decision": decision}

    def plan_skip(self, body):
        (sid,) = _req(body, "session_id")
        s = self._session(sid)
        self.store.begin_group("skip")
        return self._write_session(s, {"status": "skipped"})

    def plan_save_template(self, body):
        sid, name = _req(body, "session_id", "name")
        s = self._session(sid)
        return self.store.create("plans.templates", {"name": str(name)[:120], "type": s["type"], "sport": s.get("sport"), "duration_s": s.get("duration_s"),
                                                     "distance_m": s.get("distance_m"), "steps": s.get("steps") or [], "guiding_metric": s.get("guiding_metric")})

    def plan_update_template(self, body):
        tid, fields = _req(body, "template_id", "fields")
        allowed = {k: v for k, v in fields.items() if k in ("name", "type", "sport", "duration_s", "distance_m", "steps", "guiding_metric")}
        self.store.begin_group("template")
        tpl = self.store.update("plans.templates", tid, allowed)
        n = 0
        if body.get("apply_future"):
            today = self.snap["meta"]["build_date"]
            for s in self._raw()["plans"].get("sessions", []):
                if s.get("template_id") == tid and s["date"] >= today and s.get("status", "planned") == "planned":
                    self.store.update("plans.sessions", s["id"], {k: v for k, v in allowed.items() if k != "name"})
                    n += 1
        return dict(tpl, updated_sessions=n)

    def plan_schedule(self, body):
        """Put something on the calendar: an instant workout, a routine, a template, or a custom session."""
        (date,) = _req(body, "date")
        rec = {"date": _date(date), "steps": [], "status": "planned", "priority": body.get("priority") or "normal"}
        raw = self._raw()["plans"]
        if body.get("instant") is not None:
            opts = self.snap["plans"]["instant"].get("options") or []
            try:
                o = opts[int(body["instant"])]
            except (ValueError, IndexError, TypeError):
                raise EntryError(404, "unknown instant workout")
            rec.update(type=o["type"], title=o["title"], duration_s=o["duration_s"], distance_m=o.get("distance_m"),
                       sport="run" if o["type"] in ("AER", "LR", "REC") else None, objective=o["why"])
        elif body.get("routine_id"):
            r = next((x for x in raw.get("routines", []) if x["id"] == body["routine_id"]), None)
            if not r:
                raise EntryError(404, "unknown routine")
            rec.update(type=body.get("type") or ("STR" if r["sport"] == "strength" else "INT"), title=r["name"], sport=r["sport"],
                       steps=r["steps"], routine_id=r["id"], guiding_metric=r.get("guiding_metric"))
            rec["duration_s"] = self._steps_duration(r["steps"]) or None
        elif body.get("template_id"):
            t = next((x for x in raw.get("templates", []) if x["id"] == body["template_id"]), None)
            if not t:
                raise EntryError(404, "unknown template")
            rec.update(type=t["type"], title=t["name"], sport=t.get("sport"), duration_s=t.get("duration_s"), distance_m=t.get("distance_m"),
                       steps=t.get("steps") or [], guiding_metric=t.get("guiding_metric"), template_id=t["id"])
        else:
            typ, = _req(body, "type")
            rec.update(type=typ, title=body.get("title") or self._label(typ), sport=body.get("sport"),
                       duration_s=body.get("duration_s"), distance_m=body.get("distance_m"), objective=body.get("objective"))
        rec = {k: v for k, v in rec.items() if v is not None}
        return self.store.create("plans.sessions", rec)

    @staticmethod
    def _steps_duration(steps):
        t = 0
        for s in steps or []:
            if s.get("kind") == "repeat":
                t += (s.get("repeat") or 1) * Actions._steps_duration(s.get("steps"))
            else:
                t += s.get("duration_s") or 0
        return t

    # ------------------------------------------------------------------ thresholds
    def threshold_accept(self, body):
        metric, value = _req(body, "metric", "value")
        cands = list(self.snap["training"].get("threshold_candidates") or [])
        prop = self.snap["plans"].get("pace_proposal")
        if prop:
            cands.append({"metric": prop["metric"], "value": prop["proposed"], "method": prop["reason"], "date": self.snap["meta"]["build_date"]})
        c = next((x for x in cands if x["metric"] == metric and x["value"] == value), None)
        if not c:
            raise EntryError(404, "only a current calibration candidate can be accepted")
        note = f"accepted in app from {c['workout_id']}" if c.get("workout_id") else "accepted in app"
        return self.store.patch_profile({"physiology": {metric: {"value": c["value"], "date": c["date"], "method": c["method"], "kind": "observed", "note": note}}})

    # ------------------------------------------------------------------ nutrition
    def _tz(self):
        return tu.tzinfo(((self._raw()["profile"].get("locale") or {}).get("timezone")) or tu.DEFAULT_TZ)

    def _meal(self, mid):
        m = next((x for x in self._raw()["nutrition"].get("meals", []) if x["id"] == mid), None)
        if not m:
            raise EntryError(404, f"meal {mid!r} not found")
        return m

    def _new_meal(self, m, date, t=None):
        tz = self._tz()
        old = tu.local_dt(m["t"], tz)
        when = tu.parse_ts(t) if t else datetime.combine(tu.parse_date(date), old.timetz())
        return {"t": when.isoformat(), "meal": m.get("meal"), "name": m.get("name"), "items": m["items"], "recipe_id": m.get("recipe_id")}

    def meal_copy(self, body):
        mid, date = _req(body, "meal_id", "date")
        return self.store.create("nutrition.meals", self._new_meal(self._meal(mid), _date(date), body.get("t")))

    def meal_move(self, body):
        mid, t = _req(body, "meal_id", "t")
        try:
            tu.parse_ts(t)
        except ValueError as exc:
            raise EntryError(400, f"bad time: {exc}")
        return self.store.update("nutrition.meals", mid, {"t": t})

    def day_copy(self, body):
        src, dst = _req(body, "from", "to")
        src, dst = _date(src, "from"), _date(dst, "to")
        tz = self._tz()
        meals = [m for m in self._raw()["nutrition"].get("meals", []) if tu.local_date(m["t"], tz).isoformat() == src]
        if not meals:
            raise EntryError(404, "no meals on that day")
        self.store.begin_group("copy-day")
        return {"copied": [self.store.create("nutrition.meals", self._new_meal(m, dst))["id"] for m in meals]}

    def recipe_from_meals(self, body):
        ids, name = _req(body, "meal_ids", "name")
        items = [i for mid in ids for i in self._meal(mid)["items"]]
        return self.store.create("nutrition.recipes", {"name": str(name)[:120], "items": items, "servings": 1, "favorite": bool(body.get("favorite"))})

    def recipe_log(self, body):
        rid, t = _req(body, "recipe_id", "t")
        r = next((x for x in self._raw()["nutrition"].get("recipes", []) if x["id"] == rid), None)
        if not r:
            raise EntryError(404, "unknown recipe")
        return self.store.create("nutrition.meals", {"t": t, "meal": body.get("meal"), "name": r["name"], "items": r["items"], "recipe_id": rid})

    def recipe_plan(self, body):
        rid, date = _req(body, "recipe_id", "date")
        return self.store.create("nutrition.planned_meals", {"date": _date(date), "meal": body.get("meal"), "recipe_id": rid, "items": []})

    # ------------------------------------------------------------------ prehab
    def prehab_done(self, body):
        (rid,) = _req(body, "routine_id")
        return self.store.create("plans.prehab_log", {"routine_id": rid, "date": _date(body.get("date") or self.snap["meta"]["build_date"])})

    # ------------------------------------------------------------------ privacy & routes
    def privacy_zone_add(self, body):
        lat, lon, radius = _req(body, "lat", "lon", "radius_m")
        zones = list((self._raw()["profile"].get("privacy") or {}).get("zones") or [])
        zones.append({"id": "pz-" + secrets.token_hex(4), "label": (body.get("label") or "Private place")[:80],
                      "lat": float(lat), "lon": float(lon), "radius_m": float(radius)})
        return self.store.patch_profile({"privacy": {"zones": zones}})

    def privacy_zone_remove(self, body):
        (zid,) = _req(body, "id")
        zones = [z for z in (self._raw()["profile"].get("privacy") or {}).get("zones") or [] if z["id"] != zid]
        return self.store.patch_profile({"privacy": {"zones": zones}})

    def route_flag(self, body):
        (rid,) = _req(body, "route_id")
        ui = dict(self._raw()["profile"].get("ui") or {})
        for flag, key in (("favorite", "favorite_routes"), ("offline", "offline_routes")):
            if flag in body:
                cur = [x for x in ui.get(key) or [] if x != rid]
                if body[flag]:
                    cur.append(rid)
                ui[key] = sorted(cur)
        return self.store.patch_profile({"ui": ui})

    def route_import(self, body):
        text, = _req(body, "text")
        if len(text) > MAX_ROUTE_TEXT:
            raise EntryError(413, "route file too large (5 MB max)")
        pts = parse_route_text(text, body.get("filename") or "")
        if len(pts) < 2:
            raise EntryError(400, "no track points found (expects GPX trkpt/rtept or a GeoJSON LineString)")
        if len(pts) > MAX_ROUTE_POINTS:
            step = (len(pts) - 1) / (MAX_ROUTE_POINTS - 1)
            pts = [pts[round(i * step)] for i in range(MAX_ROUTE_POINTS)]
        rid = "import-" + secrets.token_hex(5)
        name = (body.get("name") or re.sub(r"\.(gpx|geojson|json)$", "", body.get("filename") or "", flags=re.I) or "Imported route")[:120]
        feat = {"type": "Feature", "id": rid, "geometry": {"type": "LineString", "coordinates": pts},
                "properties": {"id": rid, "kind": "route", "name": name, "sport": body.get("sport") or "run", "source": "import",
                               "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat()}}
        return self.store.create("routes.features", feat)

    # ------------------------------------------------------------------ health records
    def record_upload(self, body):
        fname, content, title = _req(body, "filename", "content_b64", "title")
        ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
        if ext not in UPLOAD_EXT:
            raise EntryError(400, "allowed files: " + ", ".join(sorted(UPLOAD_EXT)))
        try:
            raw = base64.b64decode(content, validate=True)
        except (ValueError, TypeError):
            raise EntryError(400, "content_b64 is not valid base64")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise EntryError(413, "file too large (15 MB max)")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", fname)[-80:]
        stored = f"{secrets.token_hex(6)}-{safe}"
        d = self.data_dir / "records"
        d.mkdir(exist_ok=True)
        (d / stored).write_bytes(raw)
        return self.store.create("health_records.records", {"title": str(title)[:200], "date": _date(body.get("date") or self.snap["meta"]["build_date"]),
                                                            "type": body.get("type") or "document", "provider": body.get("provider"),
                                                            "file": stored, "text": body.get("text"), "biomarkers": body.get("biomarkers") or []})


def parse_route_text(text, filename=""):
    """[[lon, lat, ele?], ...] from GPX or GeoJSON. Rejects DTDs/entities (no XML expansion attacks)."""
    t = text.lstrip()
    if t.startswith("{"):
        import json
        try:
            obj = json.loads(t)
        except ValueError:
            raise EntryError(400, "invalid GeoJSON")
        geoms = []
        if obj.get("type") == "FeatureCollection":
            geoms = [f.get("geometry") or {} for f in obj.get("features") or []]
        elif obj.get("type") == "Feature":
            geoms = [obj.get("geometry") or {}]
        else:
            geoms = [obj]
        for g in geoms:
            if g.get("type") == "LineString":
                return [_coord(c) for c in g.get("coordinates") or []]
            if g.get("type") == "MultiLineString":
                return [_coord(c) for line in g.get("coordinates") or [] for c in line]
        return []
    if re.search(r"<!DOCTYPE|<!ENTITY", t, re.I):
        raise EntryError(400, "GPX with DOCTYPE/ENTITY declarations is not accepted")
    try:
        root = ET.fromstring(t)
    except ET.ParseError:
        raise EntryError(400, "invalid GPX")
    out = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("trkpt", "rtept"):
            try:
                lat, lon = float(el.get("lat")), float(el.get("lon"))
            except (TypeError, ValueError):
                continue
            ele = next((c.text for c in el if c.tag.rsplit("}", 1)[-1] == "ele"), None)
            out.append(_coord([lon, lat] + ([float(ele)] if ele not in (None, "") else [])))
    return out


def _coord(c):
    if not isinstance(c, (list, tuple)) or len(c) < 2:
        raise EntryError(400, "bad coordinate")
    lon, lat = float(c[0]), float(c[1])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise EntryError(400, "coordinate out of range")
    return [round(lon, 6), round(lat, 6)] + ([round(float(c[2]), 1)] if len(c) > 2 and c[2] is not None else [])


ACTIONS = {
    "plan.move": Actions.plan_move, "plan.alternative": Actions.plan_alternative, "plan.adaptation": Actions.plan_adaptation,
    "plan.skip": Actions.plan_skip, "plan.save_template": Actions.plan_save_template, "plan.update_template": Actions.plan_update_template,
    "plan.schedule": Actions.plan_schedule, "threshold.accept": Actions.threshold_accept,
    "meal.copy": Actions.meal_copy, "meal.move": Actions.meal_move, "day.copy": Actions.day_copy,
    "recipe.from_meals": Actions.recipe_from_meals, "recipe.log": Actions.recipe_log, "recipe.plan": Actions.recipe_plan,
    "prehab.done": Actions.prehab_done, "privacy.zone_add": Actions.privacy_zone_add, "privacy.zone_remove": Actions.privacy_zone_remove,
    "route.flag": Actions.route_flag, "route.import": Actions.route_import, "record.upload": Actions.record_upload,
}


def run(name, store, snapshot, data_dir, body):
    fn = ACTIONS.get(name)
    if not fn:
        raise EntryError(404, f"unknown action {name!r}")
    if not isinstance(body, dict):
        raise EntryError(400, "body must be an object")
    try:
        return fn(Actions(store, snapshot, data_dir), body)
    finally:
        store.group = None
