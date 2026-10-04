"""Steve's helper scripts, accessibility contrast, metric registry, snapshot pin."""

import json
import re
import subprocess
import sys
import unittest

from helpers import SCRIPTS, empty_dir, small_synthetic_copy

from agame.entries import Store

WEB = SCRIPTS / "agame" / "web"


def run(*args):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=SCRIPTS)
    return r.returncode, r.stdout, r.stderr


STRONG = """Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE
2026-09-30 07:30:00,Lower A,45m,Back Squat,W,40,8,,,,,
2026-09-30 07:30:00,Lower A,45m,Back Squat,1,100,5,,,,,8
2026-09-30 07:30:00,Lower A,45m,Back Squat,2,100,5,,,,,8.5
2026-09-30 07:30:00,Lower A,45m,Mystery Machine,1,50,10,,,,,
"""
HEVY = """title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,set_type,weight_kg,reps,distance_km,duration_seconds,rpe
Upper,2026-10-01 18:00:00,2026-10-01 19:00:00,,Deadlift,,,0,normal,140,3,,,9
Upper,2026-10-01 18:00:00,2026-10-01 19:00:00,,Deadlift,,,1,normal,140,3,,,9
"""


class StrengthImport(unittest.TestCase):
    def test_strong_and_hevy(self):
        d = empty_dir()
        f = d / "strong.csv"
        f.write_text(STRONG)
        code, out, err = run("import_strength_csv.py", f, "--data-dir", d)
        res = json.loads(out)
        self.assertEqual(code, 2, err)  # imported, but one unknown exercise skipped
        self.assertEqual((res["format"], res["imported"]), ("strong", 1))
        self.assertIn("Mystery Machine", res["skipped_exercises"])
        s = json.loads((d / "strength.json").read_text())["sessions"][0]
        self.assertEqual((s["source"], s["kind"]), ("Strong", "user_entered"))
        self.assertEqual(s["exercises"][0]["exercise_id"], "back_squat")
        self.assertTrue(s["exercises"][0]["sets"][0]["warmup"])
        self.assertTrue(s["start"].endswith("+02:00"))  # read in the profile zone
        code, out, _ = run("import_strength_csv.py", f, "--data-dir", d)
        self.assertEqual(json.loads(out)["already_imported"], 1)
        mp = d / "map.json"
        mp.write_text(json.dumps({"Mystery Machine": "leg_press"}))
        h = d / "hevy.csv"
        h.write_text(HEVY)
        code, out, _ = run("import_strength_csv.py", h, "--data-dir", d, "--map", mp)
        self.assertEqual((code, json.loads(out)["format"]), (0, "hevy"))
        self.assertEqual(len(json.loads((d / "strength.json").read_text())["sessions"]), 2)

    def test_unknown_format_rejected(self):
        d = empty_dir()
        f = d / "x.csv"
        f.write_text("a,b,c\n1,2,3\n")
        self.assertEqual(run("import_strength_csv.py", f, "--data-dir", d)[0], 1)


class CoachScripts(unittest.TestCase):
    def test_memory_dedupe_is_one_undo(self):
        d = empty_dir()
        s = Store(d)
        for t in ("Prefers morning runs", "prefers morning runs!", "Hates treadmills"):
            s.create("coach.memory", {"type": "preference", "text": t})
        code, out, _ = run("coach_maintenance.py", "--data-dir", d)
        self.assertEqual(json.loads(out)["duplicates_removed"], 1)
        coach = json.loads((d / "coach.json").read_text())
        self.assertEqual(len(coach["memory"]), 2)
        self.assertTrue(coach["last_maintenance"])
        s.undo()
        self.assertEqual(len(json.loads((d / "coach.json").read_text())["memory"]), 3)

    def test_due_checkins(self):
        d = empty_dir()
        Store(d).create("coach.checkins", {"type": "reminder", "time": "15:00", "days": ["sun"], "text": "Creatine", "enabled": True})
        Store(d).create("coach.checkins", {"type": "reminder", "time": "09:00", "days": [], "text": "Later", "enabled": True})
        code, out, _ = run("due_checkins.py", "--data-dir", d, "--now", "2026-10-04T15:05:00+02:00", "--dist", d / "dist")
        due = json.loads(out)
        self.assertEqual([x["message"] for x in due], ["Creatine"])
        code, out, _ = run("due_checkins.py", "--data-dir", d, "--now", "2026-10-05T15:05:00+02:00", "--dist", d / "dist")
        self.assertEqual(json.loads(out), [])  # Monday: not scheduled


class Contrast(unittest.TestCase):
    """WCAG AA (4.5:1) for body, secondary and caption text, and button text, in both themes."""

    @staticmethod
    def lum(h):
        h = h.lstrip("#")
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (f(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def ratio(self, a, b):
        x, y = sorted((self.lum(a), self.lum(b)), reverse=True)
        return (x + 0.05) / (y + 0.05)

    def tokens(self):
        css = (WEB / "app.css").read_text()
        blocks = re.findall(r"(:root[^{]*)\{([^}]*)\}", css)
        dark = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", blocks[0][1]))
        light_block = next(b for sel, b in blocks if 'data-theme="light"' in sel)
        light = dict(dark, **dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", light_block)))
        return {"dark": dark, "light": light}

    def test_text_on_surfaces(self):
        for theme, t in self.tokens().items():
            for fg in ("text", "text-2", "text-3"):
                for bg in ("bg", "surface", "surface-2"):
                    self.assertGreaterEqual(self.ratio(t[fg], t[bg]), 4.5, f"{theme}: {fg} on {bg}")
            self.assertGreaterEqual(self.ratio(t["accent-ink"], t["accent"]), 4.5, f"{theme}: button text on accent")
            self.assertGreaterEqual(self.ratio(t["accent"], t["surface"]), 4.5, f"{theme}: accent links on surface")
            for st in ("ok", "warn", "bad", "info"):
                self.assertGreaterEqual(self.ratio(t[st], t["surface"]), 4.5, f"{theme}: {st} status text on surface")


class Registry(unittest.TestCase):
    def test_each_metric_defined_once(self):
        src = "\n".join(p.read_text() for p in (SCRIPTS / "agame" / "compute").glob("*.py"))
        ids = re.findall(r'@metric\("([^"]+)"', src)
        self.assertEqual(len(ids), len(set(ids)), "duplicate metric ids")
        self.assertGreater(len(ids), 20)


class SnapshotPin(unittest.TestCase):
    def test_pin_serves_kept_snapshot(self):
        from agame.build import build
        from agame.server import Config, pinned_snapshot
        from datetime import date
        d = small_synthetic_copy()
        dist = d / "dist"
        build(d, dist, date(2026, 10, 3))
        build(d, dist, date(2026, 10, 4))
        cfg = Config(d, dist, dev=True)
        self.assertIsNone(pinned_snapshot(cfg))
        (dist / "pin.txt").write_text("2026-10-03\n")
        self.assertEqual(pinned_snapshot(cfg), "2026-10-03")
        (dist / "pin.txt").write_text("../../etc/passwd")
        self.assertIsNone(pinned_snapshot(cfg))


if __name__ == "__main__":
    unittest.main()
