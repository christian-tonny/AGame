"""Results that depend only on one input's own content, reused across builds.

Keys always include a hash of the exact input (a workout's samples, a data file's content), so a changed input is
recomputed and the output stays byte-identical to an uncached build. The build keeps dist/.cache/memo.json; the server
also keeps it in memory between edits.
"""

import hashlib
import json
import os
from pathlib import Path

_STORE = {}
_USED = set()


def digest(obj):
    return hashlib.sha1(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()).hexdigest()[:20]


def samples_key(w):
    """Workout id + hash of its samples, computed once per prepared workout."""
    if "_skey" not in w:
        s = w.get("samples")
        w["_skey"] = f"{w['source_id']}:{digest(s)}" if s else None
    return w["_skey"]


def get(key, compute):
    if key is None:
        return compute()
    if key in _STORE:
        _USED.add(key)
        return _STORE[key]
    v = compute()
    _STORE[key] = v
    _USED.add(key)
    return v


def load(path):
    p = Path(path)
    if _STORE or not p.is_file():
        return
    try:
        _STORE.update(json.loads(p.read_text()))
    except (OSError, ValueError):
        pass


def save(path):
    """Write only what this build used, so the file never grows with deleted or changed inputs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: _STORE[k] for k in sorted(_USED) if k in _STORE}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(keep, separators=(",", ":")))
    os.replace(tmp, p)
    _USED.clear()


def clear():
    _STORE.clear()
    _USED.clear()
