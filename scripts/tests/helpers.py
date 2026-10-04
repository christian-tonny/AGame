"""Shared test fixtures: synthetic data and empty fixtures copied into temp dirs, cached per run."""

import atexit
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agame.paths import REPO_ROOT  # noqa: E402

os.environ.setdefault("AGAME_QUIET", "1")  # no request logs in test output
BUILD_DATE = date(2026, 10, 4)
_CACHE = {}
_TMP = Path(tempfile.mkdtemp(prefix="agame-tests-"))
atexit.register(shutil.rmtree, _TMP, True)


def synthetic_dir():
    """Read-only synthetic data dir (200 days ending BUILD_DATE). Copy before mutating."""
    if "syn" not in _CACHE:
        from agame.synthetic import write_synthetic
        out = _TMP / "syn"
        write_synthetic(out, BUILD_DATE)
        _CACHE["syn"] = out
    return _CACHE["syn"]


def copy_dir(src, name):
    dst = Path(tempfile.mkdtemp(prefix=name + "-", dir=_TMP))
    shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def empty_dir():
    """Fresh writable copy of the repo's empty fixtures."""
    return copy_dir(REPO_ROOT / "data", "empty")


def synthetic_copy():
    return copy_dir(synthetic_dir(), "syn")


def snapshot(kind="synthetic"):
    key = "snap-" + kind
    if key not in _CACHE:
        from agame.datastore import load_all
        from agame.snapshot import build_snapshot
        d = synthetic_dir() if kind == "synthetic" else REPO_ROOT / "data"
        data, problems, _ = load_all(d)
        assert not problems, problems
        _CACHE[key] = build_snapshot(data, BUILD_DATE)
    return _CACHE[key]


def walk(obj, path=""):
    """Yield (path, value) for every node."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}/{i}")


def is_value_object(x):
    return isinstance(x, dict) and "v" in x and "status" in x and "kind" in x
