"""Schema-valid empty payloads for every data file.

These are what the public repo ships in data/ (fixture: "empty"). They render as honest
empty states. Real data lives in AGAME_DATA_DIR (a private location).
"""

from agame import SCHEMA_VERSION


def _env(domain, fixture="empty"):
    return {
        "schema_version": SCHEMA_VERSION,
        "domain": domain,
        "generated_at": None,
        "as_of": None,
        "source": None,
        "fixture": fixture,
        "status": "missing",
    }


def empty_payload(domain, fixture="empty"):
    e = _env(domain, fixture)
    if domain == "profile":
        e.update({
            "athlete": {"display_name": None, "sex": None, "birth_year": None, "height_cm": None},
            "locale": {"timezone": "Africa/Kigali", "units": "metric", "week_start": "monday"},
            "physiology": {"hr_max": None, "hr_rest": None, "lthr": None, "threshold_pace_s_per_km": None,
                           "ftp_w": None, "sleep_need_base_min": None},
            "zones": {"model": "5zone", "hr_custom_bpm": None, "pace_custom_s_per_km": None},
            "schedule": {"template": []},
            "targets": {"protein_g": None, "kcal": None, "carbs_g": None, "fat_g": None, "fiber_g": None,
                        "water_ml": None, "caffeine_mg_max": None, "vegetables_g": None, "sleep_min": None,
                        "steps": None, "caffeine_cutoff": None, "wake_time": None},
            "privacy": {"hide_start_end_m": 200, "default_activity_private": False, "zones": []},
            "modules": {"cycle_tracking": False, "health_records": True, "social": True, "nutrition": True},
            "ui": {"theme": "system", "mobile_tabs": ["today", "training", "activities", "coach", "more"],
                   "app_icon": "default", "pinned_charts": [], "today_widgets": []},
            "integrations": {"map_tiles_url": None, "map_attribution": None, "nutrition_source": None,
                             "calendar_source": None, "food_database": None, "vision_service": None, "companion_app": None},
            "coach": {"personality": "data_nerd", "language": "standard", "mode": "adaptive", "include_health_records": False},
            "smart_alarm": {"enabled": False, "window_min": 30, "target_wake": None},
            "beacon": {"enabled": False, "contacts": []},
            "auto_accept_thresholds": False,
        })
    elif domain == "current":
        e.update({"domains": {}, "imports": []})
    elif domain == "metrics":
        e.update({"series": {}, "series_meta": {}})
    elif domain == "sleep":
        e.update({"nights": []})
    elif domain == "workouts":
        e.update({"workouts": []})
    elif domain == "load":
        e.update({"annotations": []})
    elif domain == "body":
        e.update({"measurements": []})
    elif domain == "nutrition":
        e.update({"connected": False, "meals": [], "water": [], "caffeine": [], "recipes": [], "favorites": [],
                  "planned_meals": [], "day_status": []})
    elif domain == "strength":
        e.update({"exercises": [], "sessions": [], "routines": [], "live_state": None, "plates": None})
    elif domain == "goals":
        e.update({"goals": []})
    elif domain == "plans":
        e.update({"plans": [], "sessions": [], "templates": [], "races": [], "calendar": [], "routines": [],
                  "prehab": [], "prehab_log": [], "mode": None})
    elif domain == "routes":
        e.update({"type": "FeatureCollection", "features": []})
    elif domain == "social":
        e.update({"connected": False, "athletes": [], "follows": [], "clubs": [], "posts": [], "kudos": [],
                  "comments": [], "challenges": [], "segment_efforts": [], "events": [], "flags": []})
    elif domain == "journal":
        e.update({"entries": [], "habits": [], "status": [], "cycle": []})
    elif domain == "health_records":
        e.update({"records": []})
    elif domain == "coach":
        e.update({"memory": [], "checkins": [], "threads": [], "last_maintenance": None})
    else:
        raise KeyError(domain)
    return e


# Record-bearing keys per domain: the public-repo guard asserts these are empty in data/.
RECORD_KEYS = {
    "current": ["imports"],
    "metrics": ["series"],
    "sleep": ["nights"],
    "workouts": ["workouts"],
    "load": ["annotations"],
    "body": ["measurements"],
    "nutrition": ["meals", "water", "caffeine", "recipes", "favorites", "planned_meals", "day_status"],
    "strength": ["exercises", "sessions", "routines"],
    "goals": ["goals"],
    "plans": ["plans", "sessions", "templates", "races", "calendar", "routines", "prehab", "prehab_log"],
    "routes": ["features"],
    "social": ["athletes", "follows", "clubs", "posts", "kudos", "comments", "challenges", "segment_efforts", "events", "flags"],
    "journal": ["entries", "habits", "status", "cycle"],
    "health_records": ["records"],
    "coach": ["memory", "checkins", "threads"],
    "profile": [],
}
