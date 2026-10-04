"""A small JSON Schema (draft 2020-12 subset) validator, standard library only.

Supported keywords: type, enum, const, properties, required, additionalProperties,
patternProperties, items, prefixItems, minItems, maxItems, minimum, maximum,
exclusiveMinimum, exclusiveMaximum, minLength, maxLength, pattern, format
(date, date-time), anyOf, oneOf, allOf, $ref (local '#/$defs/...').
"""

import re
from datetime import date, datetime

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(t)
    if py is bool:
        return isinstance(value, bool)
    return py is not None and isinstance(value, py)


def _check_format(value, fmt):
    if not isinstance(value, str):
        return True
    try:
        if fmt == "date":
            date.fromisoformat(value)
            return len(value) == 10
        if fmt == "date-time":
            s = value[:-1] + "+00:00" if value.endswith("Z") else value
            dt = datetime.fromisoformat(s)
            return dt.tzinfo is not None
    except ValueError:
        return False
    return True


class ValidationError:
    __slots__ = ("pointer", "message")

    def __init__(self, pointer, message):
        self.pointer = pointer
        self.message = message

    def as_dict(self):
        return {"pointer": self.pointer or "/", "message": self.message}

    def __repr__(self):
        return f"{self.pointer or '/'}: {self.message}"


class Validator:
    def __init__(self, schema, max_errors=200):
        self.root = schema
        self.max_errors = max_errors
        self._regex = {}

    def _resolve(self, ref):
        if not ref.startswith("#/"):
            raise ValueError(f"only local refs supported: {ref}")
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def validate(self, instance):
        errors = []
        self._v(instance, self.root, "", errors)
        return errors

    def _err(self, errors, pointer, msg):
        if len(errors) < self.max_errors:
            errors.append(ValidationError(pointer, msg))

    def _v(self, x, s, p, errors):
        if len(errors) >= self.max_errors:
            return
        if s is True or s == {}:
            return
        if s is False:
            self._err(errors, p, "not allowed")
            return
        if "$ref" in s:
            self._v(x, self._resolve(s["$ref"]), p, errors)
        t = s.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(_is_type(x, tt) for tt in types):
                self._err(errors, p, f"expected {'/'.join(types)}, got {type(x).__name__}")
                return
        if "enum" in s and x not in s["enum"]:
            self._err(errors, p, f"value {x!r} not in {s['enum']}")
        if "const" in s and x != s["const"]:
            self._err(errors, p, f"expected constant {s['const']!r}")
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if "minimum" in s and x < s["minimum"]:
                self._err(errors, p, f"{x} < minimum {s['minimum']}")
            if "maximum" in s and x > s["maximum"]:
                self._err(errors, p, f"{x} > maximum {s['maximum']}")
            if "exclusiveMinimum" in s and x <= s["exclusiveMinimum"]:
                self._err(errors, p, f"{x} <= exclusiveMinimum {s['exclusiveMinimum']}")
            if "exclusiveMaximum" in s and x >= s["exclusiveMaximum"]:
                self._err(errors, p, f"{x} >= exclusiveMaximum {s['exclusiveMaximum']}")
        if isinstance(x, str):
            if "minLength" in s and len(x) < s["minLength"]:
                self._err(errors, p, f"shorter than {s['minLength']}")
            if "maxLength" in s and len(x) > s["maxLength"]:
                self._err(errors, p, f"longer than {s['maxLength']}")
            if "pattern" in s:
                rx = self._regex.get(s["pattern"])
                if rx is None:
                    rx = self._regex[s["pattern"]] = re.compile(s["pattern"])
                if not rx.search(x):
                    self._err(errors, p, f"does not match pattern {s['pattern']}")
            if "format" in s and not _check_format(x, s["format"]):
                self._err(errors, p, f"invalid {s['format']}: {x!r}")
        if isinstance(x, dict):
            props = s.get("properties", {})
            for req in s.get("required", []):
                if req not in x:
                    self._err(errors, p, f"missing required property '{req}'")
            pat = s.get("patternProperties", {})
            for k, v in x.items():
                cp = f"{p}/{k}"
                if k in props:
                    self._v(v, props[k], cp, errors)
                    continue
                matched = False
                for rxs, sub in pat.items():
                    if re.search(rxs, k):
                        matched = True
                        self._v(v, sub, cp, errors)
                if matched:
                    continue
                ap = s.get("additionalProperties", True)
                if ap is False:
                    self._err(errors, cp, "additional property not allowed")
                elif isinstance(ap, dict):
                    self._v(v, ap, cp, errors)
        if isinstance(x, list):
            if "minItems" in s and len(x) < s["minItems"]:
                self._err(errors, p, f"fewer than {s['minItems']} items")
            if "maxItems" in s and len(x) > s["maxItems"]:
                self._err(errors, p, f"more than {s['maxItems']} items")
            prefix = s.get("prefixItems")
            start = 0
            if prefix:
                for i, sub in enumerate(prefix[: len(x)]):
                    self._v(x[i], sub, f"{p}/{i}", errors)
                start = len(prefix)
            items = s.get("items")
            if isinstance(items, dict):
                for i in range(start, len(x)):
                    self._v(x[i], items, f"{p}/{i}", errors)
                    if len(errors) >= self.max_errors:
                        break
        for sub in s.get("allOf", []):
            self._v(x, sub, p, errors)
        if "anyOf" in s:
            if not any(not Validator(self.root)._sub(x, sub) for sub in s["anyOf"]):
                self._err(errors, p, "does not match any allowed shape (anyOf)")
        if "oneOf" in s:
            n = sum(1 for sub in s["oneOf"] if not Validator(self.root)._sub(x, sub))
            if n != 1:
                self._err(errors, p, f"must match exactly one shape (oneOf), matched {n}")

    def _sub(self, x, s):
        errs = []
        self._v(x, s, "", errs)
        return errs


def validate(instance, schema):
    return Validator(schema).validate(instance)
