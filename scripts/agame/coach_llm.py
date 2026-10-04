"""Optional conversational Coach backed by Claude (server-side only).

Enabled when AGAME_LLM_PROVIDER=anthropic and the `anthropic` package is installed
(pip install anthropic). Credentials come from the environment (ANTHROPIC_API_KEY or an
`ant auth login` profile) - never from code or the browser.

Grounding: the model sees only AGame's computed snapshot (HealthKit-derived numbers) plus
the coach memory store. No Strava data exists in AGame, and health records are excluded
unless profile.coach.include_health_records is true. Ghost Mode requests are not logged
or persisted. The model is told to cite metric keys and never diagnose.
"""

import json
import os

DEFAULT_MODEL = "claude-opus-5-5"
EFFORT_BY_MODE = {"fast": "low", "adaptive": "medium", "thinking": "high"}
PERSONALITY = {
    "data_nerd": "Precise and numbers-first. Lead with the metric and its delta.",
    "guardian": "Calm and protective of long-term health. Favour recovery when signals conflict.",
    "friend": "Warm and encouraging, still factual.",
    "commander": "Direct and action-oriented. One clear instruction first.",
}

SYSTEM = """You are AGame Coach, a fitness coach for one athlete. You answer from the JSON snapshot provided, which is computed from the athlete's own Apple HealthKit data.
Rules:
- Use only numbers present in the snapshot. If something is missing, say it is missing; never estimate or invent a measurement.
- Cite the snapshot keys and dates you used in square brackets, e.g. [today.rings.recovery 2026-10-04].
- This is fitness information, not medical advice. Never diagnose, never name conditions, and suggest a clinician for health concerns.
- Keep answers short: a direct answer first, then at most three supporting facts.
- If asked for a chart, reply with one line of JSON {"chart": {"metric": "<metric key>", "days": N}} after your answer; the app renders it from real data.
- Research citations: only cite a source if one is included in the snapshot; never fabricate citations."""


def enabled():
    if os.environ.get("AGAME_LLM_PROVIDER", "").lower() != "anthropic":
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def context_from_snapshot(snap, activity_id=None, include_records=False):
    """Compact, grounded context. Only computed AGame values."""
    t = snap["today"]
    ctx = {
        "date": snap["meta"]["build_date"], "timezone": snap["meta"]["timezone"], "data_status": snap["meta"]["data_status"]["overall"],
        "today": {"rings": t["rings"], "recommendation": t["recommendation"], "action": t["action"], "plan": t["plan"],
                  "since_yesterday": t["since_yesterday"], "load": t["load"], "goals": t["goals"]},
        "recovery_components": (snap["recovery"].get("today") or {}).get("components"),
        "sleep": {k: snap["sleep"].get(k) for k in ("score", "need", "debt", "regularity", "avg_7", "avg_30", "last_date")},
        "training_status": snap["training"]["status"], "weekly_effort": snap["training"]["weekly_effort"],
        "predictions": snap["training"]["predictions"], "weight": {k: snap["body"]["weight"].get(k) for k in ("current", "trend_kg_per_week", "goal")},
        "vo2max": {k: snap["body"]["vo2max"].get(k) for k in ("current", "delta_30", "delta_90", "confidence")},
        "nutrition_protein": (snap["nutrition"] or {}).get("protein"),
        "recent_activities": snap["activities"]["list"][:12],
        "upcoming_sessions": snap["plans"]["upcoming"][:6],
        "helping_hurting_90d": [r for r in snap["coach"]["helping_hurting"].get("90", []) if r["status"] == "ok"],
        "memory": snap["coach"]["memory"],
    }
    if activity_id and activity_id in snap["activities"]["details"]:
        det = snap["activities"]["details"][activity_id]
        ctx["activity"] = {k: det.get(k) for k in ("row", "zones", "splits", "verdict", "laps", "intervals", "gap", "hr_curve", "efficiency_factor",
                                                    "intensity_pct", "decoupling_pct", "efforts", "matched", "planned", "insights", "weather")}
    if include_records:
        ctx["health_records"] = snap["health"]["records"]["biomarkers"]
    return ctx


def ask(question, snap, mode="adaptive", personality="data_nerd", activity_id=None, include_records=False, history=None):
    import anthropic

    client = anthropic.Anthropic()
    model = os.environ.get("AGAME_LLM_MODEL") or DEFAULT_MODEL
    context = context_from_snapshot(snap, activity_id, include_records)
    system = [{"type": "text", "text": SYSTEM + "\nTone: " + PERSONALITY.get(personality, PERSONALITY["data_nerd"]), "cache_control": {"type": "ephemeral"}}]
    msgs = []
    for m in (history or [])[-8:]:
        msgs.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["text"]})
    msgs.append({"role": "user", "content": "Snapshot (JSON):\n" + json.dumps(context, sort_keys=True, default=str) + "\n\nQuestion: " + question})
    kwargs = dict(model=model, max_tokens=16000, system=system, messages=msgs,
                  output_config={"effort": EFFORT_BY_MODE.get(mode, "medium")})
    try:
        # Server-side refusal fallback (Claude API): routes declined requests to a fallback model.
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        return {"text": "I can't help with that one. Try asking about your training, sleep or recovery data.", "citations": [], "chart": None,
                "model": resp.model, "refused": True}
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    chart = None
    lines = text.splitlines()
    if lines and lines[-1].strip().startswith('{"chart"'):
        try:
            chart = json.loads(lines[-1])["chart"]
            text = "\n".join(lines[:-1]).strip()
        except (ValueError, KeyError):
            chart = None
    return {"text": text, "citations": [], "chart": chart, "model": resp.model, "refused": False}
