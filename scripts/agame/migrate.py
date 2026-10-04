"""In-memory schema migrations.

Policy (docs/data-contract.md): every file carries schema_version (semver).
- Same major, lower minor/patch -> migrate in memory with a warning, then validate.
- Version newer than this code knows -> hard failure (never guess).
Migrations are pure functions registered per (domain, from_version).
"""

from agame import SCHEMA_VERSION


def _v(s):
    return tuple(int(x) for x in s.split("."))


def _m_sleep_090(p):
    if "nights" not in p and "sessions" in p:
        p["nights"] = p.pop("sessions")
    return p


def _m_workouts_090(p):
    for w in p.get("workouts", []):
        if "sport" not in w and "type" in w:
            w["sport"] = w.pop("type")
    return p


# (domain or "*", from_version) -> (fn, to_version)
MIGRATIONS = {
    ("sleep", "0.9.0"): (_m_sleep_090, "1.0.0"),
    ("workouts", "0.9.0"): (_m_workouts_090, "1.0.0"),
    ("*", "0.9.0"): (lambda p: p, "1.0.0"),
}


class MigrationError(Exception):
    pass


def migrate(domain, payload):
    """Return (payload, warnings). Raises MigrationError for unknown/newer versions."""
    warnings = []
    ver = payload.get("schema_version")
    if not isinstance(ver, str):
        raise MigrationError(f"{domain}: missing schema_version")
    try:
        cur = _v(ver)
    except ValueError:
        raise MigrationError(f"{domain}: invalid schema_version {ver!r}")
    target = _v(SCHEMA_VERSION)
    if cur > target:
        raise MigrationError(f"{domain}: schema_version {ver} is newer than supported {SCHEMA_VERSION}; update AGame")
    if cur[0] != target[0] and cur[0] != 0:
        raise MigrationError(f"{domain}: major version {ver} cannot be migrated to {SCHEMA_VERSION}")
    steps = 0
    while ver != SCHEMA_VERSION:
        key = (domain, ver) if (domain, ver) in MIGRATIONS else ("*", ver)
        if key not in MIGRATIONS:
            raise MigrationError(f"{domain}: no migration path from {ver}")
        fn, to = MIGRATIONS[key]
        # apply domain-specific and then generic shims
        payload = fn(dict(payload))
        if key[0] != "*" and ("*", ver) in MIGRATIONS:
            payload = MIGRATIONS[("*", ver)][0](payload)
        warnings.append(f"{domain}: migrated in memory {ver} -> {to}")
        ver = to
        payload["schema_version"] = ver
        payload.setdefault("domain", domain)
        steps += 1
        if steps > 20:
            raise MigrationError(f"{domain}: migration loop")
    return payload, warnings
