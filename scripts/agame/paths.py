"""Filesystem locations and configuration loading."""

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
SCHEMA_DIR = REPO_ROOT / "schemas"
WEB_DIR = Path(__file__).resolve().parent / "web"

DATA_FILES = [
    "profile.json",
    "current.json",
    "metrics.json",
    "sleep.json",
    "workouts.json",
    "load.json",
    "body.json",
    "nutrition.json",
    "strength.json",
    "goals.json",
    "plans.json",
    "routes.geojson",
    "social.json",
    "journal.json",
    "health_records.json",
    "coach.json",
]


def domain_of(filename):
    return filename.split(".")[0]


def data_dir(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGAME_DATA_DIR")
    return Path(env).resolve() if env else (REPO_ROOT / "data")


def dist_dir(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGAME_DIST_DIR")
    return Path(env).resolve() if env else (REPO_ROOT / "dist")


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(profile=None):
    """Algorithm defaults merged with optional profile['overrides']."""
    with open(CONFIG_DIR / "defaults.json", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if profile and isinstance(profile.get("overrides"), dict):
        cfg = _deep_merge(cfg, profile["overrides"])
    return cfg


def load_exercise_library():
    with open(CONFIG_DIR / "exercises.json", encoding="utf-8") as fh:
        return json.load(fh)
