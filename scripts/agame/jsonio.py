"""JSON helpers: canonical (deterministic) serialisation and atomic writes."""

import json
import math
import os
import tempfile
from pathlib import Path


def _normalise(obj, ndigits):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        r = round(obj, ndigits)
        if r == int(r) and abs(r) < 1e15:
            # keep a float marker-free integer form for stability (1.0 -> 1)
            return int(r)
        return r
    if isinstance(obj, dict):
        return {str(k): _normalise(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalise(v, ndigits) for v in obj]
    return obj


def canonical_dumps(obj, ndigits=4, indent=None):
    """Byte-stable JSON: sorted keys, rounded floats, no NaN."""
    norm = _normalise(obj, ndigits)
    if indent is None:
        return json.dumps(norm, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(norm, sort_keys=True, indent=indent, ensure_ascii=False)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_json(path, obj, indent=1):
    atomic_write_text(path, canonical_dumps(obj, ndigits=6, indent=indent) + "\n")


def atomic_write_many(pairs):
    """All-or-nothing write of several files: stage every temp file, then rename all.

    pairs: list of (path, text). If staging fails nothing is replaced.
    """
    staged = []
    try:
        for path, text in pairs:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            staged.append((tmp, path))
    except BaseException:
        for tmp, _ in staged:
            if os.path.exists(tmp):
                os.unlink(tmp)
        raise
    for tmp, path in staged:
        os.replace(tmp, path)
