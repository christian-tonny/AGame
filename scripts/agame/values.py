"""Value objects carried into computed.json.

Every displayed number travels with provenance so the UI can show freshness and
never confuse missing with zero.
"""

KINDS = ("observed", "configured", "computed", "estimated", "user_entered")
STATUSES = ("ok", "partial", "stale", "missing", "calibrating")


def mv(v, unit=None, kind="computed", as_of=None, status=None, source=None,
       coverage=None, method=None, inputs=None, note=None, **extra):
    """Make a metric value. v=None always means unknown (status 'missing')."""
    if status is None:
        status = "missing" if v is None else "ok"
    if v is None and status == "ok":
        status = "missing"
    out = {"v": v, "unit": unit, "kind": kind, "as_of": as_of, "status": status}
    if source is not None:
        out["source"] = source
    if coverage is not None:
        out["coverage"] = coverage
    if method is not None:
        out["method"] = method
    if inputs is not None:
        out["inputs"] = inputs
    if note is not None:
        out["note"] = note
    out.update(extra)
    return out


def missing(unit=None, note=None, method=None, kind="computed"):
    return mv(None, unit=unit, kind=kind, status="missing", note=note, method=method)


def latest_as_of(*values):
    """Max of non-null ISO timestamps (string compare is safe for same-format ISO)."""
    cands = [v for v in values if v]
    return max(cands) if cands else None


def worst_status(*statuses):
    order = {"ok": 0, "calibrating": 1, "partial": 2, "stale": 3, "missing": 4}
    st = [s for s in statuses if s]
    if not st:
        return "missing"
    return max(st, key=lambda s: order.get(s, 0))
