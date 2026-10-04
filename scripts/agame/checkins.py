"""Coach check-ins: which are due now and when each one runs next. Shared by due_checkins.py and GET /api/agent/checkins."""

import json
from datetime import datetime, timedelta
from pathlib import Path

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _at(c, day, tz):
    try:
        hh, mm = (int(x) for x in c["time"].split(":")[:2])
    except (ValueError, KeyError, AttributeError):
        return None
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)


def _runs_on(c, day):
    return not c.get("days") or DAYS[day.weekday()] in c["days"]


def due(checkins, now, window_min):
    out = []
    start = now - timedelta(minutes=window_min)
    for c in checkins:
        if not c.get("enabled", True):
            continue
        for day in (now.date(), now.date() - timedelta(days=1)):
            at = _at(c, day, now.tzinfo)
            if at and start < at <= now and _runs_on(c, day):
                out.append((c, at))
    return out


def next_run(c, now):
    for k in range(0, 8):
        day = now.date() + timedelta(days=k)
        at = _at(c, day, now.tzinfo)
        if at and at > now and _runs_on(c, day):
            return at
    return None


def facts(dist):
    def read(name):
        p = Path(dist) / name
        return json.loads(p.read_text()) if p.exists() else None
    weekly = read("weekly_review.json")
    return {"morning_report": read("morning_summary.json"), "weekly_summary": weekly, "monthly_summary": weekly}


def message(c):
    return c.get("text") or c["type"].replace("_", " ").capitalize()


def report(checkins, now, window_min, dist):
    """Due check-ins (with the computed facts to include) plus the full schedule, so an agent can plan its own wake-ups."""
    f = facts(dist)
    due_now = [{"id": c["id"], "type": c["type"], "scheduled_for": at.isoformat(), "message": message(c), "facts": f.get(c["type"])}
               for c, at in due(checkins, now, window_min)]
    schedule = []
    for c in checkins:
        if not c.get("enabled", True):
            continue
        nr = next_run(c, now)
        schedule.append({"id": c["id"], "type": c["type"], "time": c.get("time"), "days": c.get("days") or DAYS,
                         "next_at": nr.isoformat() if nr else None, "message": message(c)})
    schedule.sort(key=lambda x: x["next_at"] or "~")
    return {"now": now.isoformat(), "window_min": window_min, "due": due_now, "schedule": schedule}
