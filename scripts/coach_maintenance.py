#!/usr/bin/env python3
"""Overnight Coach memory maintenance (the agent runs this after the morning build).

Removes exact and near-duplicate memories (same type, same normalised text), keeping the most
recently updated one, and trims chat threads to the configured limit. Every removal goes through
the entries Store, so it is in the edit history and can be undone as one step.

Usage:
  python3 scripts/coach_maintenance.py [--data-dir DIR] [--dry-run] [--keep-threads 50]
Exit 0 always on success; 1 if the data dir is unreadable.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agame.entries import EntryError, Store  # noqa: E402
from agame.jsonio import atomic_write_text, canonical_dumps  # noqa: E402
from agame.paths import data_dir  # noqa: E402


def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-threads", type=int, default=50)
    a = ap.parse_args(argv)
    store = Store(data_dir(a.data_dir), actor="maintenance")
    try:
        data = store._load()
    except EntryError as exc:
        print(json.dumps({"status": "failed", "error": exc.message}))
        return 1
    mem = data["coach"].get("memory", [])
    keep = {}
    for m in sorted(mem, key=lambda m: (m.get("updated_at") or m.get("created_at") or "")):
        if m["type"] == "artifact":
            continue
        keep[(m["type"], norm(m["text"]))] = m["id"]
    dupes = [m for m in mem if m["type"] != "artifact" and keep.get((m["type"], norm(m["text"]))) != m["id"]]
    threads = data["coach"].get("threads", [])
    trimmed = max(0, len(threads) - a.keep_threads)
    if not a.dry_run:
        if dupes:
            store.begin_group("coach-maintenance")
            for m in dupes:
                store.delete("coach.memory", m["id"])
        data = store._load()
        c = data["coach"]
        c["threads"] = c.get("threads", [])[-a.keep_threads:]
        c["last_maintenance"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        store._validate_and_write(data, "coach")
    print(json.dumps({"status": "ok", "duplicates_removed": len(dupes), "threads_trimmed": trimmed, "dry_run": a.dry_run}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
