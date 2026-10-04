"""Server-side owner actions: plans, thresholds, nutrition, prehab, privacy zones, routes, record uploads; grouped undo."""

import base64
import json
import unittest

from helpers import BUILD_DATE, small_synthetic_copy

from agame import actions
from agame.datastore import load_all
from agame.entries import EntryError, Store
from agame.snapshot import build_snapshot


class ActionCase(unittest.TestCase):
    def setUp(self):
        self.d = small_synthetic_copy()
        self.store = Store(self.d)

    def snap(self):
        data, _, _ = load_all(self.d)
        return build_snapshot(data, BUILD_DATE)[0]

    def run_action(self, name, body):
        return actions.run(name, self.store, self.snap(), self.d, body)

    def raw(self, f):
        return json.loads((self.d / f).read_text())


class Plans(ActionCase):
    def test_move_plan_session_and_undo(self):
        s = next(x for x in self.snap()["plans"]["upcoming"] if x["origin"] == "plan" and x["date"] > BUILD_DATE.isoformat())
        self.run_action("plan.move", {"session_id": s["id"], "date": "2026-10-09"})
        moved = next(x for x in self.raw("plans.json")["sessions"] if x["id"] == s["id"])
        self.assertEqual(moved["date"], "2026-10-09")
        self.store.undo()
        self.assertEqual(next(x for x in self.raw("plans.json")["sessions"] if x["id"] == s["id"])["date"], s["date"])

    def test_move_template_session_is_one_undo(self):
        plans = self.raw("plans.json")
        plans["sessions"] = []
        (self.d / "plans.json").write_text(json.dumps(plans))
        s = next(x for x in self.snap()["plans"]["upcoming"] if x["origin"] == "template" and x["type"] != "REST")
        self.run_action("plan.move", {"session_id": s["id"], "date": "2026-10-10"})
        sessions = self.raw("plans.json")["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertEqual({x["date"] for x in sessions}, {s["date"], "2026-10-10"})
        self.store.undo()
        self.assertEqual(self.raw("plans.json")["sessions"], [])

    def test_wizard_alternative(self):
        s = next(x for x in self.snap()["plans"]["upcoming"] if x.get("alternatives"))
        alt = next(a for a in s["alternatives"] if a["kind"] == "shorter")
        rec = self.run_action("plan.alternative", {"session_id": s["id"], "kind": "shorter"})
        self.assertEqual(rec["duration_s"], alt["duration_s"])
        self.assertIn("Was:", rec["objective"])
        with self.assertRaises(EntryError):
            self.run_action("plan.alternative", {"session_id": s["id"], "kind": "made-up"})

    def test_adaptation_accept_and_decline_hide_it(self):
        snap = self.snap()
        a = snap["plans"]["adaptations"][0]
        self.run_action("plan.adaptation", {"session_id": a["session_id"], "rule": a["rule"], "decision": "declined"})
        self.assertNotIn((a["session_id"], a["rule"]), {(x["session_id"], x["rule"]) for x in self.snap()["plans"]["adaptations"]})
        self.store.undo()
        self.run_action("plan.adaptation", {"session_id": a["session_id"], "rule": a["rule"], "decision": "accepted"})
        s = next(x for x in self.raw("plans.json")["sessions"] if x["date"] == a["date"])
        self.assertEqual(s["type"], a["to"])
        self.assertIn(a["reason"], s["objective"])

    def test_schedule_instant_template_and_custom(self):
        r1 = self.run_action("plan.schedule", {"date": "2026-10-11", "instant": 0})
        self.assertEqual(r1["type"], self.snap()["plans"]["instant"]["options"][0]["type"])
        tpl = self.run_action("plan.save_template", {"session_id": r1["id"], "name": "My easy run"})
        r2 = self.run_action("plan.schedule", {"date": "2026-10-12", "template_id": tpl["id"]})
        self.assertEqual(r2["template_id"], tpl["id"])
        out = self.run_action("plan.update_template", {"template_id": tpl["id"], "fields": {"duration_s": 2700}, "apply_future": True})
        self.assertEqual(out["updated_sessions"], 1)
        self.assertEqual(next(x for x in self.raw("plans.json")["sessions"] if x["id"] == r2["id"])["duration_s"], 2700)
        r3 = self.run_action("plan.schedule", {"date": "2026-10-13", "type": "TMP", "duration_s": 3000})
        self.assertEqual(r3["title"], "Tempo")

    def test_schedule_routine_uses_its_steps(self):
        rt = self.raw("plans.json")["routines"][0]
        rec = self.run_action("plan.schedule", {"date": "2026-10-14", "routine_id": rt["id"]})
        self.assertEqual(rec["steps"], rt["steps"])
        self.assertGreater(rec["duration_s"], 0)


class Thresholds(ActionCase):
    def test_only_real_candidates_accepted(self):
        c = self.snap()["training"]["threshold_candidates"][-1]
        with self.assertRaises(EntryError):
            self.run_action("threshold.accept", {"metric": c["metric"], "value": c["value"] + 1})
        self.run_action("threshold.accept", {"metric": c["metric"], "value": c["value"]})
        ph = self.raw("profile.json")["physiology"][c["metric"]]
        self.assertEqual((ph["value"], ph["kind"]), (c["value"], "observed"))


class Nutrition(ActionCase):
    def test_copy_meal_day_and_recipe(self):
        meals = self.raw("nutrition.json")["meals"]
        m = meals[-1]
        rec = self.run_action("meal.copy", {"meal_id": m["id"], "date": "2026-10-04"})
        self.assertTrue(rec["t"].startswith("2026-10-04"))
        self.assertEqual(rec["kind"], "user_entered")
        src_day = m["t"][:10]
        out = self.run_action("day.copy", {"from": src_day, "to": "2026-10-05"})
        self.assertGreaterEqual(len(out["copied"]), 1)
        self.store.undo()  # whole day in one step
        self.assertFalse([x for x in self.raw("nutrition.json")["meals"] if x["t"].startswith("2026-10-05")])
        r = self.run_action("recipe.from_meals", {"meal_ids": [m["id"]], "name": "Usual breakfast"})
        self.assertEqual(r["items"], m["items"])
        self.run_action("recipe.plan", {"recipe_id": r["id"], "date": "2026-10-06", "meal": "breakfast"})
        logged = self.run_action("recipe.log", {"recipe_id": r["id"], "t": "2026-10-04T08:00:00+02:00", "meal": "breakfast"})
        self.assertEqual(logged["recipe_id"], r["id"])

    def test_naive_time_rejected(self):
        m = self.raw("nutrition.json")["meals"][-1]
        with self.assertRaises(EntryError):
            self.run_action("meal.move", {"meal_id": m["id"], "t": "2026-10-04T08:00:00"})


class Misc(ActionCase):
    def test_prehab_done(self):
        rid = self.raw("plans.json")["prehab"][0]["id"]
        self.run_action("prehab.done", {"routine_id": rid})
        self.assertTrue(any(x["routine_id"] == rid and x["date"] == BUILD_DATE.isoformat() for x in self.raw("plans.json")["prehab_log"]))

    def test_privacy_zone_add_remove(self):
        self.run_action("privacy.zone_add", {"label": "Office", "lat": -1.95, "lon": 30.06, "radius_m": 200})
        zones = self.raw("profile.json")["privacy"]["zones"]
        z = next(x for x in zones if x["label"] == "Office")
        self.run_action("privacy.zone_remove", {"id": z["id"]})
        self.assertNotIn(z["id"], [x["id"] for x in self.raw("profile.json")["privacy"]["zones"]])

    def test_route_flags_and_import(self):
        rid = self.snap()["routes"]["library"][0]["id"]
        self.run_action("route.flag", {"route_id": rid, "favorite": True, "offline": True})
        lib = {r["id"]: r for r in self.snap()["routes"]["library"]}
        self.assertTrue(lib[rid]["favorite"] and lib[rid]["offline"])
        gpx = '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>' + "".join(
            f'<trkpt lat="{-1.95 + i * 0.0003}" lon="{30.05 + i * 0.0002}"><ele>{1500 + i}</ele></trkpt>' for i in range(40)) + "</trkseg></trk></gpx>"
        rec = self.run_action("route.import", {"filename": "hill.gpx", "text": gpx})
        lib = {r["id"]: r for r in self.snap()["routes"]["library"]}
        self.assertIn(rec["id"], lib)
        self.assertTrue(lib[rec["id"]]["imported"])
        self.assertEqual(lib[rec["id"]]["name"], "hill")
        with self.assertRaises(EntryError):
            self.run_action("route.import", {"filename": "x.gpx", "text": '<!DOCTYPE x [<!ENTITY a "b">]><gpx/>'})
        geo = json.dumps({"type": "LineString", "coordinates": [[30.0, -1.9], [30.01, -1.91]]})
        self.assertEqual(self.run_action("route.import", {"filename": "r.geojson", "text": geo})["geometry"]["coordinates"][0], [30.0, -1.9])

    def test_record_upload(self):
        pdf = base64.b64encode(b"%PDF-1.4 test").decode()
        rec = self.run_action("record.upload", {"filename": "lab results.pdf", "content_b64": pdf, "title": "Blood panel", "type": "lab"})
        self.assertTrue((self.d / "records" / rec["file"]).is_file())
        with self.assertRaises(EntryError):
            self.run_action("record.upload", {"filename": "x.exe", "content_b64": pdf, "title": "nope"})

    def test_manual_blood_pressure_feeds_series(self):
        self.store.create("body.measurements", {"t": "2026-10-04T07:00:00+02:00", "type": "bp_systolic_mmhg", "v": 118})
        self.store.create("body.measurements", {"t": "2026-10-04T07:00:00+02:00", "type": "bp_diastolic_mmhg", "v": 76})
        bp = self.snap()["body"]["bp"]
        self.assertEqual(bp["systolic"]["latest"], 118)
        self.assertEqual(bp["diastolic"]["latest"], 76)

    def test_unknown_action(self):
        with self.assertRaises(EntryError):
            self.run_action("rm.rf", {})


if __name__ == "__main__":
    unittest.main()
