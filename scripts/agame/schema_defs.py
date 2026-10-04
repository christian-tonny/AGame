"""Source of truth for the checked-in JSON Schemas in schemas/.

Regenerate with:  python3 -m agame.schema_defs --write   (run from scripts/)
A unit test fails if schemas/ drifts from these definitions.
"""

import json
import sys
from pathlib import Path

SEMVER = r"^\d+\.\d+\.\d+$"
ID = {"type": "string", "minLength": 1, "maxLength": 200}
TS = {"type": "string", "format": "date-time"}
TS_N = {"type": ["string", "null"], "format": "date-time"}
DATE = {"type": "string", "format": "date"}
DATE_N = {"type": ["string", "null"], "format": "date"}
NUM_N = {"type": ["number", "null"]}
INT_N = {"type": ["integer", "null"]}
STR_N = {"type": ["string", "null"]}
BOOL_N = {"type": ["boolean", "null"]}
KIND = {"enum": ["observed", "configured", "computed", "estimated", "user_entered"]}
SPORTS = ["run", "trail_run", "treadmill_run", "track_run", "walk", "hike", "ride", "virtual_ride",
          "swim", "open_water_swim", "row", "strength", "hiit", "yoga", "mobility", "elliptical",
          "multisport", "other"]


def envelope(domain, extra_props, required_extra=()):
    props = {
        "schema_version": {"type": "string", "pattern": SEMVER},
        "domain": {"const": domain},
        "generated_at": TS_N,
        "as_of": TS_N,
        "source": STR_N,
        "fixture": {"enum": [False, "empty", "synthetic"]},
        "status": {"enum": ["ok", "partial", "stale", "missing"]},
        "coverage": {
            "type": ["object", "null"],
            "properties": {"expected": INT_N, "received": INT_N, "ratio": NUM_N},
            "additionalProperties": False,
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    }
    props.update(extra_props)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"agame/{domain}.schema.json",
        "title": f"AGame {domain}",
        "type": "object",
        "required": ["schema_version", "domain", "generated_at", "as_of", "source", "status"] + list(required_extra),
        "properties": props,
        "additionalProperties": False,
    }


def defs():
    return {
        "measure": {
            "description": "A configured or observed number with provenance.",
            "type": ["object", "null"],
            "required": ["value"],
            "properties": {
                "value": {"type": "number"},
                "method": STR_N,
                "date": DATE_N,
                "kind": KIND,
                "note": STR_N,
            },
            "additionalProperties": False,
        },
        "point": {
            "type": "object",
            "required": ["v", "source_id"],
            "properties": {
                "t": TS,
                "date": DATE,
                "v": {"type": "number"},
                "source_id": ID,
                "source": STR_N,
                "kind": KIND,
            },
            "additionalProperties": False,
            "anyOf": [{"required": ["t"]}, {"required": ["date"]}],
        },
        "step": {
            "type": "object",
            "required": ["kind"],
            "properties": {
                "kind": {"enum": ["warmup", "work", "recovery", "cooldown", "repeat", "rest"]},
                "label": STR_N,
                "duration_s": NUM_N,
                "distance_m": NUM_N,
                "target": {
                    "type": ["object", "null"],
                    "properties": {
                        "metric": {"enum": ["hr", "pace", "power", "zone", "rpe", "open"]},
                        "low": NUM_N,
                        "high": NUM_N,
                        "zone": INT_N,
                    },
                    "additionalProperties": False,
                },
                "repeat": INT_N,
                "steps": {"type": "array", "items": {"$ref": "#/$defs/step"}},
            },
            "additionalProperties": False,
        },
        "set": {
            "type": "object",
            "required": ["reps"],
            "properties": {
                "reps": {"type": "integer", "minimum": 0, "maximum": 1000},
                "weight_kg": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
                "rpe": {"type": ["number", "null"], "minimum": 1, "maximum": 10},
                "rir": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                "warmup": {"type": "boolean"},
                "rest_s": NUM_N,
                "duration_s": NUM_N,
            },
            "additionalProperties": False,
        },
    }


def schema_profile():
    s = envelope("profile", {
        "athlete": {
            "type": "object",
            "properties": {
                "display_name": STR_N,
                "sex": {"enum": ["male", "female", None]},
                "birth_year": {"type": ["integer", "null"], "minimum": 1900, "maximum": 2100},
                "height_cm": {"type": ["number", "null"], "minimum": 50, "maximum": 260},
            },
            "additionalProperties": False,
        },
        "locale": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
                "units": {"enum": ["metric", "imperial"]},
                "week_start": {"enum": ["monday", "sunday", "saturday"]},
            },
            "additionalProperties": False,
        },
        "physiology": {
            "type": "object",
            "properties": {
                "hr_max": {"$ref": "#/$defs/measure"},
                "hr_rest": {"$ref": "#/$defs/measure"},
                "lthr": {"$ref": "#/$defs/measure"},
                "threshold_pace_s_per_km": {"$ref": "#/$defs/measure"},
                "ftp_w": {"$ref": "#/$defs/measure"},
                "sleep_need_base_min": {"$ref": "#/$defs/measure"},
            },
            "additionalProperties": False,
        },
        "zones": {
            "type": "object",
            "properties": {
                "model": {"enum": ["5zone", "7zone"]},
                "hr_custom_bpm": {"type": ["array", "null"], "items": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "minItems": 2, "maxItems": 2}},
                "pace_custom_s_per_km": {"type": ["array", "null"], "items": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "minItems": 2, "maxItems": 2}},
            },
            "additionalProperties": False,
        },
        "schedule": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["weekday", "intent"],
                        "properties": {
                            "weekday": {"enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
                            "intent": {"enum": ["run", "lift", "rest", "optional_run", "cross_train", "mobility"]},
                            "duration_s": NUM_N,
                            "type": STR_N,
                            "available_from": STR_N,
                            "available_to": STR_N,
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "targets": {
            "type": "object",
            "properties": {k: NUM_N for k in [
                "protein_g", "kcal", "carbs_g", "fat_g", "fiber_g", "water_ml", "caffeine_mg_max",
                "vegetables_g", "sleep_min", "steps"]} | {"caffeine_cutoff": STR_N, "wake_time": STR_N},
            "additionalProperties": False,
        },
        "privacy": {
            "type": "object",
            "properties": {
                "hide_start_end_m": NUM_N,
                "default_activity_private": {"type": "boolean"},
                "zones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "lat", "lon", "radius_m"],
                        "properties": {
                            "id": ID, "label": STR_N,
                            "lat": {"type": "number", "minimum": -90, "maximum": 90},
                            "lon": {"type": "number", "minimum": -180, "maximum": 180},
                            "radius_m": {"type": "number", "minimum": 0, "maximum": 5000},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "modules": {
            "type": "object",
            "properties": {k: {"type": "boolean"} for k in ["cycle_tracking", "health_records", "social", "nutrition"]},
            "additionalProperties": False,
        },
        "ui": {
            "type": "object",
            "properties": {
                "theme": {"enum": ["system", "dark", "light"]},
                "mobile_tabs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
                "app_icon": {"type": "string"},
                "pinned_charts": {"type": "array", "items": {"type": "string"}},
                "today_widgets": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "integrations": {
            "type": "object",
            "properties": {
                "map_tiles_url": STR_N,
                "map_attribution": STR_N,
                "nutrition_source": STR_N,
                "calendar_source": STR_N,
                "food_database": STR_N,
                "vision_service": STR_N,
                "companion_app": STR_N,
            },
            "additionalProperties": False,
        },
        "coach": {
            "type": "object",
            "properties": {
                "personality": {"enum": ["data_nerd", "guardian", "friend", "commander"]},
                "language": {"enum": ["simple", "standard", "technical"]},
                "mode": {"enum": ["fast", "thinking", "adaptive"]},
                "include_health_records": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "smart_alarm": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}, "window_min": NUM_N, "target_wake": STR_N},
            "additionalProperties": False,
        },
        "beacon": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}, "contacts": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        "auto_accept_thresholds": {"type": "boolean"},
        "overrides": {"type": "object"},
    })
    s["$defs"] = defs()
    return s


def schema_current():
    dom = {
        "type": "object",
        "properties": {
            "last_sync": TS_N,
            "last_sample": TS_N,
            "expected_for": DATE_N,
            "received": BOOL_N,
            "status": {"enum": ["ok", "partial", "stale", "missing"]},
            "note": STR_N,
        },
        "additionalProperties": False,
    }
    return envelope("current", {
        "domains": {"type": "object", "additionalProperties": dom},
        "imports": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["idempotency_key", "date", "at"],
                "properties": {
                    "idempotency_key": ID, "date": DATE, "at": TS,
                    "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                },
                "additionalProperties": False,
            },
        },
    }, required_extra=("domains",))


def schema_metrics():
    s = envelope("metrics", {
        "series": {
            "type": "object",
            "patternProperties": {r"^[a-z0-9_]+$": {"type": "array", "items": {"$ref": "#/$defs/point"}}},
            "additionalProperties": False,
        },
        "series_meta": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["unit"],
                "properties": {"unit": {"type": "string"}, "label": STR_N, "agg": {"enum": ["mean", "sum", "last", "max", "min"]},
                               "better": {"enum": ["higher", "lower", None]}},
                "additionalProperties": False,
            },
        },
    }, required_extra=("series",))
    s["$defs"] = defs()
    return s


def schema_sleep():
    seg = {
        "type": "object",
        "required": ["stage", "start", "end"],
        "properties": {
            "stage": {"enum": ["in_bed", "awake", "core", "deep", "rem", "asleep_unspecified"]},
            "start": TS, "end": TS,
        },
        "additionalProperties": False,
    }
    night = {
        "type": "object",
        "required": ["source_id", "start", "end", "segments"],
        "properties": {
            "source_id": ID, "date": DATE, "start": TS, "end": TS, "source": STR_N,
            "is_nap": {"type": "boolean"},
            "segments": {"type": "array", "items": seg},
        },
        "additionalProperties": False,
    }
    return envelope("sleep", {"nights": {"type": "array", "items": night}}, required_extra=("nights",))


def schema_workouts():
    arr = {"type": "array", "items": NUM_N}
    w = {
        "type": "object",
        "required": ["source_id", "sport", "start", "end"],
        "properties": {
            "source_id": ID,
            "sport": {"enum": SPORTS},
            "name": STR_N,
            "start": TS, "end": TS,
            "duration_s": {"type": ["number", "null"], "minimum": 0},
            "moving_s": {"type": ["number", "null"], "minimum": 0},
            "distance_m": {"type": ["number", "null"], "minimum": 0},
            "elevation_gain_m": {"type": ["number", "null"], "minimum": 0},
            "active_kcal": {"type": ["number", "null"], "minimum": 0},
            "avg_hr": NUM_N, "max_hr": NUM_N, "avg_cadence": NUM_N, "avg_power_w": NUM_N,
            "source": STR_N, "device": STR_N, "indoor": BOOL_N,
            "route_id": STR_N,
            "samples": {
                "type": ["object", "null"],
                "required": ["t"],
                "properties": {k: arr for k in ["t", "hr", "dist_m", "elev_m", "cadence", "power_w", "lat", "lon", "speed_mps",
                                                 "gct_ms", "vo_cm", "stride_m", "temp_c"]},
                "additionalProperties": False,
            },
            "laps": {
                "type": ["array", "null"],
                "items": {
                    "type": "object", "required": ["start_s", "end_s"],
                    "properties": {"start_s": {"type": "number"}, "end_s": {"type": "number"}, "distance_m": NUM_N, "label": STR_N},
                    "additionalProperties": False,
                },
            },
            "segments": {
                "type": ["array", "null"],
                "items": {
                    "type": "object", "required": ["sport", "start_s", "end_s"],
                    "properties": {"sport": {"enum": SPORTS + ["transition"]}, "start_s": {"type": "number"}, "end_s": {"type": "number"}, "distance_m": NUM_N},
                    "additionalProperties": False,
                },
            },
            "weather": {
                "type": ["object", "null"],
                "properties": {"temp_c": NUM_N, "humidity_pct": NUM_N, "wind_kph": NUM_N, "conditions": STR_N, "source": STR_N},
                "additionalProperties": False,
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    return envelope("workouts", {"workouts": {"type": "array", "items": w}}, required_extra=("workouts",))


def schema_load():
    e = {
        "type": "object",
        "required": ["id", "workout_id"],
        "properties": {
            "id": ID, "workout_id": ID,
            "rpe": {"type": ["number", "null"], "minimum": 1, "maximum": 10},
            "feel": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
            "comment": STR_N, "title": STR_N,
            "private": {"type": "boolean"}, "race": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "created_at": TS_N, "updated_at": TS_N,
        },
        "additionalProperties": False,
    }
    return envelope("load", {"annotations": {"type": "array", "items": e}}, required_extra=("annotations",))


def schema_body():
    m = {
        "type": "object",
        "required": ["t", "type", "v", "source_id"],
        "properties": {
            "t": TS,
            "type": {"enum": ["weight_kg", "body_fat_pct", "lean_mass_kg", "waist_cm", "bmi"]},
            "v": {"type": "number", "minimum": 0},
            "source_id": ID, "source": STR_N, "kind": KIND,
        },
        "additionalProperties": False,
    }
    return envelope("body", {"measurements": {"type": "array", "items": m}}, required_extra=("measurements",))


def schema_nutrition():
    item = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"}, "qty": NUM_N, "unit": STR_N, "barcode": STR_N,
            "kcal": NUM_N, "protein_g": NUM_N, "carbs_g": NUM_N, "fat_g": NUM_N, "fiber_g": NUM_N,
            "sugar_g": NUM_N, "sodium_mg": NUM_N, "caffeine_mg": NUM_N, "water_ml": NUM_N,
            "food_groups": {"type": ["object", "null"], "additionalProperties": {"type": "number"}},
            "micros": {"type": ["object", "null"], "additionalProperties": {"type": "number"}},
        },
        "additionalProperties": False,
    }
    meal = {
        "type": "object",
        "required": ["id", "t", "items"],
        "properties": {
            "id": ID, "t": TS, "name": STR_N,
            "meal": {"enum": ["breakfast", "lunch", "dinner", "snack", "pre_workout", "post_workout", None]},
            "items": {"type": "array", "items": item},
            "source_id": STR_N, "kind": KIND, "photo": STR_N, "recipe_id": STR_N,
        },
        "additionalProperties": False,
    }
    recipe = {
        "type": "object", "required": ["id", "name", "items"],
        "properties": {"id": ID, "name": {"type": "string"}, "servings": NUM_N, "items": {"type": "array", "items": item}, "favorite": {"type": "boolean"}},
        "additionalProperties": False,
    }
    planned = {
        "type": "object", "required": ["id", "date"],
        "properties": {"id": ID, "date": DATE, "meal": STR_N, "recipe_id": STR_N, "items": {"type": "array", "items": item}},
        "additionalProperties": False,
    }
    simple = lambda field: {
        "type": "object", "required": ["t", field],
        "properties": {"t": TS, field: {"type": "number", "minimum": 0}, "source_id": STR_N, "kind": KIND},
        "additionalProperties": False,
    }
    return envelope("nutrition", {
        "connected": {"type": "boolean"},
        "meals": {"type": "array", "items": meal},
        "water": {"type": "array", "items": simple("ml")},
        "caffeine": {"type": "array", "items": simple("mg")},
        "glucose_note": STR_N,
        "recipes": {"type": "array", "items": recipe},
        "favorites": {"type": "array", "items": item},
        "planned_meals": {"type": "array", "items": planned},
        "day_status": {
            "type": "array",
            "items": {"type": "object", "required": ["date", "complete"],
                      "properties": {"date": DATE, "complete": {"type": "boolean"}}, "additionalProperties": False},
        },
    }, required_extra=("connected", "meals"))


def schema_strength():
    ex = {
        "type": "object",
        "required": ["exercise_id", "sets"],
        "properties": {"exercise_id": ID, "sets": {"type": "array", "items": {"$ref": "#/$defs/set"}}, "notes": STR_N, "superset": STR_N},
        "additionalProperties": False,
    }
    session = {
        "type": "object",
        "required": ["id", "start", "exercises"],
        "properties": {
            "id": ID, "workout_id": STR_N, "start": TS, "end": TS_N, "name": STR_N,
            "exercises": {"type": "array", "items": ex}, "notes": STR_N, "kind": KIND, "source": STR_N,
        },
        "additionalProperties": False,
    }
    lib = {
        "type": "object",
        "required": ["id", "name", "primary"],
        "properties": {
            "id": ID, "name": {"type": "string"},
            "primary": {"type": "array", "items": {"type": "string"}},
            "secondary": {"type": "array", "items": {"type": "string"}},
            "equipment": STR_N, "pattern": STR_N, "cue": STR_N,
        },
        "additionalProperties": False,
    }
    routine = {
        "type": "object", "required": ["id", "name", "exercises"],
        "properties": {
            "id": ID, "name": {"type": "string"},
            "exercises": {"type": "array", "items": {
                "type": "object", "required": ["exercise_id"],
                "properties": {"exercise_id": ID, "sets": INT_N, "reps": STR_N, "rpe": NUM_N, "rest_s": NUM_N, "notes": STR_N},
                "additionalProperties": False}},
        },
        "additionalProperties": False,
    }
    s = envelope("strength", {
        "exercises": {"type": "array", "items": lib},
        "sessions": {"type": "array", "items": session},
        "routines": {"type": "array", "items": routine},
        "live_state": {
            "description": "Companion contract: in-progress session for future phone/watch sync.",
            "type": ["object", "null"],
            "properties": {
                "session_id": ID, "routine_id": STR_N, "started_at": TS,
                "exercise_index": {"type": "integer"}, "set_index": {"type": "integer"},
                "rest_started_at": TS_N, "device": STR_N,
            },
            "additionalProperties": False,
        },
        "plates": {
            "type": ["object", "null"],
            "properties": {"bar_kg": {"type": "number"}, "plates_kg": {"type": "array", "items": {"type": "number"}}},
            "additionalProperties": False,
        },
    }, required_extra=("sessions",))
    s["$defs"] = defs()
    return s


def schema_goals():
    g = {
        "type": "object",
        "required": ["id", "type", "title"],
        "properties": {
            "id": ID,
            "type": {"enum": ["distance", "time", "elevation", "calories", "kilojoules", "load", "streak", "record",
                              "segment", "strength", "body_weight", "nutrition", "habit", "sessions"]},
            "title": {"type": "string"},
            "target": NUM_N, "start_value": NUM_N, "unit": STR_N,
            "sport": STR_N, "metric": STR_N, "exercise_id": STR_N, "segment_id": STR_N, "distance_m": NUM_N,
            "period": {
                "type": "object",
                "required": ["type"],
                "properties": {"type": {"enum": ["week", "month", "year", "custom", "by_date"]}, "start": DATE_N, "end": DATE_N},
                "additionalProperties": False,
            },
            "direction": {"enum": ["increase", "decrease", None]},
            "status": {"enum": ["active", "archived", "done"]},
            "created_at": TS_N, "kind": KIND,
        },
        "additionalProperties": False,
    }
    return envelope("goals", {"goals": {"type": "array", "items": g}}, required_extra=("goals",))


def schema_plans():
    session = {
        "type": "object",
        "required": ["id", "date", "type"],
        "properties": {
            "id": ID, "plan_id": STR_N, "date": DATE, "type": {"type": "string"},
            "sport": STR_N, "title": STR_N, "duration_s": NUM_N, "distance_m": NUM_N, "load_planned": NUM_N,
            "steps": {"type": "array", "items": {"$ref": "#/$defs/step"}},
            "guiding_metric": {"enum": ["hr", "pace", "power", "rpe", None]},
            "objective": STR_N, "priority": {"enum": ["key", "normal", "optional", None]},
            "template_id": STR_N, "routine_id": STR_N, "linked_workout_id": STR_N,
            "status": {"enum": ["planned", "done", "missed", "skipped", "moved"]},
            "forecast_temp_c": NUM_N, "start_time": STR_N, "kind": KIND,
        },
        "additionalProperties": False,
    }
    return_ = envelope("plans", {
        "plans": {"type": "array", "items": {
            "type": "object", "required": ["id", "name"],
            "properties": {"id": ID, "name": {"type": "string"}, "goal": STR_N, "race_id": STR_N, "start": DATE_N, "end": DATE_N,
                           "mode": {"enum": ["race", "maintain", "build", None]},
                           "phases": {"type": "array", "items": {"type": "object", "required": ["name", "start", "end"],
                                                                 "properties": {"name": {"type": "string"}, "start": DATE, "end": DATE, "focus": STR_N},
                                                                 "additionalProperties": False}},
                           "created_by": STR_N},
            "additionalProperties": False}},
        "sessions": {"type": "array", "items": session},
        "templates": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "type"],
            "properties": {"id": ID, "name": {"type": "string"}, "type": {"type": "string"}, "sport": STR_N, "duration_s": NUM_N,
                           "distance_m": NUM_N, "steps": {"type": "array", "items": {"$ref": "#/$defs/step"}}, "guiding_metric": STR_N},
            "additionalProperties": False}},
        "races": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "date"],
            "properties": {"id": ID, "name": {"type": "string"}, "date": DATE, "distance_m": NUM_N, "priority": {"enum": ["A", "B", "C"]},
                           "goal_time_s": NUM_N, "location": STR_N},
            "additionalProperties": False}},
        "calendar": {"type": "array", "items": {
            "type": "object", "required": ["id", "title", "start", "end"],
            "properties": {"id": ID, "title": {"type": "string"}, "start": TS, "end": TS, "source": STR_N, "busy": {"type": "boolean"}},
            "additionalProperties": False}},
        "routines": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "sport", "steps"],
            "properties": {"id": ID, "name": {"type": "string"}, "sport": {"type": "string"}, "steps": {"type": "array", "items": {"$ref": "#/$defs/step"}},
                           "guiding_metric": STR_N, "notes": STR_N},
            "additionalProperties": False}},
        "prehab": {"type": "array", "items": {
            "type": "object", "required": ["id", "name"],
            "properties": {"id": ID, "name": {"type": "string"}, "focus": STR_N, "duration_min": NUM_N,
                           "exercises": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False}},
        "prehab_log": {"type": "array", "items": {
            "type": "object", "required": ["id", "date", "routine_id"],
            "properties": {"id": ID, "date": DATE, "routine_id": ID}, "additionalProperties": False}},
        "mode": {"enum": ["race", "maintain", None]},
    }, required_extra=("sessions",))
    return_["$defs"] = defs()
    return return_


def schema_routes():
    s = envelope("routes", {
        "type": {"const": "FeatureCollection"},
        "features": {"type": "array", "items": {
            "type": "object",
            "required": ["type", "properties", "geometry"],
            "properties": {
                "type": {"const": "Feature"},
                "id": STR_N,
                "properties": {
                    "type": "object",
                    "required": ["id", "kind"],
                    "properties": {
                        "id": ID, "kind": {"enum": ["route", "trace", "segment"]}, "name": STR_N,
                        "workout_id": STR_N, "sport": STR_N, "favorite": {"type": "boolean"}, "offline": {"type": "boolean"},
                        "surface": {"type": ["object", "null"], "properties": {"paved_pct": NUM_N, "unpaved_pct": NUM_N, "unknown_pct": NUM_N},
                                    "additionalProperties": False},
                        "difficulty": STR_N, "source": STR_N, "created_at": TS_N, "kind_detail": STR_N,
                    },
                    "additionalProperties": False,
                },
                "geometry": {
                    "type": "object",
                    "required": ["type", "coordinates"],
                    "properties": {
                        "type": {"const": "LineString"},
                        "coordinates": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "number"}}},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        }},
    }, required_extra=("type", "features"))
    return s


def schema_social():
    any_list = {"type": "array", "items": {"type": "object", "required": ["id", "source"], "properties": {"id": ID, "source": {"type": "string"}, "consent": {"type": "boolean"}}}}
    return envelope("social", {
        "connected": {"type": "boolean"},
        "athletes": any_list, "follows": any_list, "clubs": any_list, "posts": any_list,
        "kudos": any_list, "comments": any_list, "challenges": any_list, "segment_efforts": any_list,
        "events": any_list, "flags": any_list,
    }, required_extra=("connected",))


def schema_journal():
    return envelope("journal", {
        "entries": {"type": "array", "items": {
            "type": "object", "required": ["id", "date", "type"],
            "properties": {
                "id": ID, "date": DATE, "t": TS_N,
                "type": {"enum": ["mood", "hydration", "sunlight", "screen_time", "caffeine", "alcohol", "symptom", "travel",
                                  "sickness", "habit", "note", "supplement", "stress"]},
                "value": NUM_N, "unit": STR_N, "text": STR_N, "habit_id": STR_N, "kind": KIND,
            },
            "additionalProperties": False}},
        "habits": {"type": "array", "items": {
            "type": "object", "required": ["id", "name"],
            "properties": {"id": ID, "name": {"type": "string"}, "unit": STR_N, "boolean": {"type": "boolean"}}, "additionalProperties": False}},
        "activity_status": {"type": "array", "items": {
            "type": "object", "required": ["id", "status", "start"],
            "properties": {"id": ID, "status": {"enum": ["normal", "sick", "traveling", "injured", "recovering"]},
                           "start": DATE, "end": DATE_N, "source": STR_N, "note": STR_N},
            "additionalProperties": False}},
        "cycle": {"type": "array", "items": {
            "type": "object", "required": ["date"],
            "properties": {"date": DATE, "flow": {"enum": ["none", "light", "medium", "heavy", None]}, "phase": STR_N, "source": STR_N, "symptoms": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False}},
    }, required_extra=("entries",))


def schema_health_records():
    bm = {
        "type": "object", "required": ["name", "value", "unit"],
        "properties": {"name": {"type": "string"}, "code": STR_N, "value": {"type": "number"}, "unit": {"type": "string"},
                       "ref_low": NUM_N, "ref_high": NUM_N, "ref_text": STR_N},
        "additionalProperties": False,
    }
    return envelope("health_records", {
        "records": {"type": "array", "items": {
            "type": "object", "required": ["id", "date", "type", "title"],
            "properties": {"id": ID, "date": DATE, "type": {"enum": ["lab", "note", "document", "imaging", "vaccination"]},
                           "title": {"type": "string"}, "provider": STR_N, "file": STR_N, "text": STR_N,
                           "biomarkers": {"type": "array", "items": bm}, "kind": KIND},
            "additionalProperties": False}},
    }, required_extra=("records",))


def schema_coach():
    return envelope("coach", {
        "memory": {"type": "array", "items": {
            "type": "object", "required": ["id", "type", "text"],
            "properties": {"id": ID, "type": {"enum": ["preference", "goal", "correction", "fact", "artifact"]},
                           "text": {"type": "string"}, "created_at": TS_N, "updated_at": TS_N, "spec": {"type": ["object", "null"]}},
            "additionalProperties": False}},
        "checkins": {"type": "array", "items": {
            "type": "object", "required": ["id", "type", "time"],
            "properties": {"id": ID, "type": {"enum": ["morning_report", "reminder", "goal_progress", "weekly_summary", "monthly_summary", "nudge"]},
                           "time": {"type": "string"}, "days": {"type": "array", "items": {"type": "string"}},
                           "text": STR_N, "enabled": {"type": "boolean"}},
            "additionalProperties": False}},
        "threads": {"type": "array", "items": {
            "type": "object", "required": ["id", "messages"],
            "properties": {"id": ID, "title": STR_N, "created_at": TS_N, "activity_id": STR_N,
                           "messages": {"type": "array", "items": {"type": "object", "required": ["role", "text"],
                                                                     "properties": {"role": {"enum": ["user", "coach"]}, "text": {"type": "string"},
                                                                                    "t": TS_N, "citations": {"type": "array"}, "chart": {"type": ["object", "null"]}},
                                                                     "additionalProperties": False}}},
            "additionalProperties": False}},
        "last_maintenance": TS_N,
    }, required_extra=("memory",))


ALL = {
    "profile": schema_profile,
    "current": schema_current,
    "metrics": schema_metrics,
    "sleep": schema_sleep,
    "workouts": schema_workouts,
    "load": schema_load,
    "body": schema_body,
    "nutrition": schema_nutrition,
    "strength": schema_strength,
    "goals": schema_goals,
    "plans": schema_plans,
    "routes": schema_routes,
    "social": schema_social,
    "journal": schema_journal,
    "health_records": schema_health_records,
    "coach": schema_coach,
}


def build_all():
    return {name: fn() for name, fn in ALL.items()}


def write(schema_dir):
    schema_dir = Path(schema_dir)
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, sch in build_all().items():
        (schema_dir / f"{name}.schema.json").write_text(json.dumps(sch, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from agame.paths import SCHEMA_DIR
    if "--write" in sys.argv:
        write(SCHEMA_DIR)
        print(f"wrote {len(ALL)} schemas to {SCHEMA_DIR}")
    else:
        print(json.dumps(build_all(), indent=1)[:2000])
