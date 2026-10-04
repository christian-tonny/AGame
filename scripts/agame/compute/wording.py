"""Every sentence AGame says about today, built once. The app and morning_summary.json show these same strings.

Rules (docs/design.md): say what to do and why in plain words, no jargon, no raw metrics pasted into a sentence.
"""

import re

from agame import timeutil as tu

FACTOR_PHRASE = {
    "recovery": "low recovery", "sleep": "short sleep", "sleep_debt": "sleep debt", "hrv": "a dip in HRV",
    "rhr": "a raised resting heart rate", "form": "built-up fatigue", "ramp": "a fast ramp in load",
    "strain_yday": "yesterday's strain", "status": "how you're feeling", "resp": "a higher breathing rate",
    "overtraining": "signs of overreaching",
}
SESSION_LABEL = {"AER": "Aerobic", "REC": "Recovery", "REST": "Rest", "MOB": "Mobility"}
SWAP_TO = {"AER": "an easy aerobic session", "REC": "a recovery session", "REST": "a rest day", "MOB": "mobility work"}
RECOVERY_HEADLINE = {"high": "High recovery", "low": "Low recovery"}


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def hm(seconds):
    if not seconds:
        return None
    m = round(seconds / 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def day_label(iso):
    d = tu.parse_date(iso)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def coach_line(rec, plan, action=None, sleep_missing=False):
    """One or two sentences: what to do today and why, from the call and its strongest factors.
    While last night's sleep is missing, older sleep is not given as a reason."""
    skip = {"sleep", "sleep_debt"} if sleep_missing else set()
    hurting = [FACTOR_PHRASE.get(f["id"], f["label"].lower()) for f in rec.get("factors", []) if f.get("direction") == "hurting" and f["id"] not in skip][:2]
    session = next((s for s in plan or [] if s.get("type") != "REST"), None)
    what = _name(session.get("title") or session.get("label") or "today's session") if session else None
    call = rec.get("call")
    because = f"{_cap(_join(hurting))} {'are' if len(hurting) > 1 else 'is'} " if hurting else ""
    if call == "reduce":
        easy = "gentle" if what and "easy" in what else "easy"
        return (because + "holding your recovery back. " if because else "") + f"Keep {'the ' + what if what else 'today'} {easy} and conversational."
    if call == "rest":
        return (because + "weighing on you. " if because else "") + "Take the day off and let your body catch up."
    if call == "train":
        return "You're recovered and ready. " + (f"Go ahead with the {what} as planned." if what else "A good day for a quality session.")
    if call == "rest_day":
        return "Rest day on your plan. Enjoy it, and get to bed on time."
    if call == "open":
        return "Nothing planned today. Move if you feel like it."
    return (action or {}).get("text") or "Not enough data for a call yet."


def _name(s):
    """A session title as it reads inside a sentence: "Aerobic (optional)" -> "aerobic"."""
    return re.sub(r"\s*\(.*?\)", "", s).strip().lower()


def _session(sessions, sid):
    return next((s for s in sessions if s.get("id") == sid), None)


def adaptation(a, sessions):
    """Title and subline the app shows on the suggestion, and the sentence the agent sends. All from the same facts."""
    s = _session(sessions, a.get("session_id")) or {}
    name = s.get("title") or s.get("label") or "session"
    dur = hm(s.get("duration_s"))
    act = a.get("action")
    if act == "swap":
        title = f"Swap to {SESSION_LABEL.get(a.get('to'), a.get('to'))}"
        sub = f"Instead of {name}" + (f" · {dur}" if dur else "")
        sentence = f"swap the {_name(name)} for {SWAP_TO.get(a.get('to'), 'an easier session')}"
    elif act == "shorten":
        pct = round(a.get("factor", 1) * 100)
        title, sub = f"Shorten to {pct}%", name + (f" · {dur} now" if dur else "")
        sentence = f"shorten the {_name(name)} to {pct}% of the plan"
    elif act == "move":
        title, sub = f"Move to {day_label(a['to_date'])}", name
        sentence = f"move the {_name(name)} to {tu.parse_date(a['to_date']).strftime('%A')}"
    elif act == "adjust_pace":
        title, sub = f"Run {a.get('pct_slower')}% slower", name
        sentence = f"run the {_name(name)} about {a.get('pct_slower')}% slower"
    else:
        title, sub, sentence = _cap(str(act).replace("_", " ")), name, f"{str(act).replace('_', ' ')} the {_name(name)}"
    return {"title": title, "sub": sub, "sentence": f"Suggested in the app: {sentence}."}


def recovery_headline(score):
    if not score or score.get("v") is None:
        return None
    return RECOVERY_HEADLINE.get(score.get("band"), "Moderate recovery")


def recovery_line(rings, sleep_v, sleep_missing):
    """How you recovered, in one sentence. Says plainly when last night's sleep has not reached AGame yet."""
    rec = (rings or {}).get("recovery") or {}
    if sleep_missing:
        if rec.get("v") is not None:
            return f"Last night's sleep hasn't synced from your phone yet, so your {rec['v']}% recovery may change."
        return "Last night's sleep hasn't synced from your phone yet, so there is no recovery score this morning."
    if rec.get("v") is None:
        return "There is no recovery score yet; it needs two weeks of HRV and resting heart rate."
    head = RECOVERY_HEADLINE.get(rec.get("band"), "Moderate recovery")
    slept = f" after {hm(sleep_v * 60)} of sleep" if sleep_v else ""
    return f"{head} at {rec['v']}%{slept}."


def morning_message(rings, sleep_v, sleep_missing, coach, suggestion):
    lines = [recovery_line(rings, sleep_v, sleep_missing), coach]
    if suggestion:
        lines.append(suggestion["sentence"])
    return [x for x in lines if x]
