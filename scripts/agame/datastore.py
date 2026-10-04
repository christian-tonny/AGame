"""Load every data file (migrated in memory) into one dict keyed by domain."""

import json
from pathlib import Path

from agame.empty import empty_payload
from agame.migrate import MigrationError, migrate
from agame.paths import DATA_FILES, domain_of


class LoadError(Exception):
    pass


def load_all(data_dir, allow_missing_files=True):
    """Return (data, problems, warnings).

    problems: list of {file, pointer, message, severity='error'} for unreadable files.
    Missing files are replaced by empty payloads (status missing) with a warning,
    so a partial morning sync can still build.
    """
    data_dir = Path(data_dir)
    data, problems, warnings = {}, [], []
    for fname in DATA_FILES:
        dom = domain_of(fname)
        path = data_dir / fname
        if not path.exists():
            if allow_missing_files:
                data[dom] = empty_payload(dom, fixture=False)
                warnings.append(f"{fname}: file missing, treated as empty")
                continue
            problems.append({"file": fname, "pointer": "/", "message": "file missing", "severity": "error"})
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append({"file": fname, "pointer": "/", "message": f"unreadable JSON: {exc}", "severity": "error"})
            continue
        if not isinstance(payload, dict):
            problems.append({"file": fname, "pointer": "/", "message": "top level must be an object", "severity": "error"})
            continue
        try:
            payload, w = migrate(dom, payload)
            warnings.extend(w)
        except MigrationError as exc:
            problems.append({"file": fname, "pointer": "/schema_version", "message": str(exc), "severity": "error"})
            continue
        data[dom] = payload
    return data, problems, warnings
