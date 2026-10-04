"""Assemble the self-contained dashboard HTML (inline CSS, data, JS)."""

from agame.jsonio import canonical_dumps
from agame.paths import WEB_DIR

JS_ORDER = [
    "core.js", "ui.js", "charts.js",
    "screen_today.js", "screen_training.js", "screen_activities.js", "screen_recovery_sleep.js",
    "screen_strength.js", "screen_nutrition_body.js", "screen_more.js", "edits.js",
    "app.js",
]


def _read(name):
    return (WEB_DIR / name).read_text(encoding="utf-8")


def embedded_json(snapshot):
    """Canonical JSON safe to embed in <script type=application/json>."""
    s = canonical_dumps(snapshot, ndigits=4)
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


def render_html(snapshot):
    html = _read("index.html")
    css = _read("app.css")
    js = "\n;\n".join(_read(n) for n in JS_ORDER)
    # Replace placeholders in a fixed order; data last so it cannot inject placeholders.
    html = html.replace("{{CSS}}", css).replace("{{JS}}", js.replace("</script", "<\\/script"))
    return html.replace("{{DATA}}", embedded_json(snapshot))
