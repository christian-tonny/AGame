"""User-entered records: create/update/delete, history with before/after, undo, export, delete-all, read-only imports."""

import json
import unittest

from helpers import empty_dir, synthetic_copy

from agame.entries import EntryError, Store


class Entries(unittest.TestCase):
    def setUp(self):
        self.d = empty_dir()
        self.s = Store(self.d)

    def journal(self):
        return json.loads((self.d / "journal.json").read_text())["entries"]

    def test_create_update_delete_with_history(self):
        rec = self.s.create("journal.entries", {"date": "2026-10-04", "type": "mood", "value": 4})
        self.assertEqual(rec["kind"], "user_entered")
        self.s.update("journal.entries", rec["id"], {"value": 2})
        self.assertEqual(self.journal()[0]["value"], 2)
        self.s.delete("journal.entries", rec["id"])
        self.assertEqual(self.journal(), [])
        h = self.s.history()
        self.assertEqual([x["op"] for x in h], ["delete", "update", "create"])
        upd = h[1]
        self.assertEqual((upd["before"]["value"], upd["after"]["value"]), (4, 2))

    def test_undo_walks_back(self):
        rec = self.s.create("journal.entries", {"date": "2026-10-04", "type": "mood", "value": 4})
        self.s.update("journal.entries", rec["id"], {"value": 1})
        self.s.undo()
        self.assertEqual(self.journal()[0]["value"], 4)
        self.s.undo()
        self.assertEqual(self.journal(), [])
        with self.assertRaises(EntryError) as cm:
            self.s.undo()
        self.assertEqual(cm.exception.status, 404)

    def test_undo_delete_restores(self):
        rec = self.s.create("journal.entries", {"date": "2026-10-04", "type": "note", "text": "felt good"})
        self.s.delete("journal.entries", rec["id"])
        self.s.undo()
        self.assertEqual(self.journal()[0]["text"], "felt good")

    def test_invalid_change_rejected_and_not_written(self):
        before = (self.d / "journal.json").read_bytes()
        with self.assertRaises(EntryError) as cm:
            self.s.create("journal.entries", {"date": "2026-10-04", "type": "not-a-type"})
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual((self.d / "journal.json").read_bytes(), before)
        self.assertEqual(self.s.history(), [])

    def test_unknown_collection(self):
        with self.assertRaises(EntryError) as cm:
            self.s.create("workouts.workouts", {})
        self.assertEqual(cm.exception.status, 404)

    def test_profile_patch_whitelist_and_undo(self):
        self.s.patch_profile({"targets": {"protein_g": 150}})
        prof = json.loads((self.d / "profile.json").read_text())
        self.assertEqual(prof["targets"]["protein_g"], 150)
        self.assertIsNone(prof["targets"]["kcal"])  # merged, not replaced
        with self.assertRaises(EntryError):
            self.s.patch_profile({"schema_version": "9.9.9"})
        self.s.undo()
        self.assertIsNone(json.loads((self.d / "profile.json").read_text())["targets"]["protein_g"])

    def test_annotation_upsert(self):
        a = self.s.create("load.annotations", {"workout_id": "w1", "rpe": 6})
        b = self.s.create("load.annotations", {"workout_id": "w1", "rpe": 8})
        self.assertEqual(a["id"], b["id"])
        anns = json.loads((self.d / "load.json").read_text())["annotations"]
        self.assertEqual([x["rpe"] for x in anns], [8])

    def test_export_and_delete_all(self):
        self.s.create("journal.entries", {"date": "2026-10-04", "type": "mood", "value": 4})
        self.s.create("body.measurements", {"t": "2026-10-04T07:00:00+02:00", "type": "weight_kg", "v": 80.1})
        exp = self.s.export()
        self.assertEqual(exp["contract"], "agame.export.v1")
        self.assertIn("journal.entries", exp["collections"])
        with self.assertRaises(EntryError):
            self.s.delete_all_user_entered("yes")
        self.assertEqual(self.s.delete_all_user_entered("DELETE-MY-ENTRIES"), 2)
        self.assertEqual(self.journal(), [])


class ImportedRecordsAreReadOnly(unittest.TestCase):
    def test_healthkit_measurement_cannot_be_edited_or_deleted(self):
        d = synthetic_copy()
        s = Store(d)
        body = json.loads((d / "body.json").read_text())
        sid = next(m["source_id"] for m in body["measurements"] if m.get("kind") != "user_entered")
        for op in (lambda: s.update("body.measurements", sid, {"v": 1}), lambda: s.delete("body.measurements", sid)):
            with self.assertRaises(EntryError) as cm:
                op()
            self.assertEqual(cm.exception.status, 409)
        self.assertEqual(json.loads((d / "body.json").read_text()), body)

    def test_create_cannot_spoof_kind_or_reuse_id(self):
        d = synthetic_copy()
        s = Store(d)
        rec = s.create("body.measurements", {"t": "2026-10-04T07:00:00+02:00", "type": "weight_kg", "v": 80.1, "kind": "observed"})
        self.assertEqual(rec["kind"], "user_entered")
        sid = json.loads((d / "body.json").read_text())["measurements"][0]["source_id"]
        with self.assertRaises(EntryError) as cm:
            s.create("body.measurements", {"source_id": sid, "t": "2026-10-04T07:00:00+02:00", "type": "weight_kg", "v": 80.1})
        self.assertEqual(cm.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
