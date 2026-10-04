"""All AGame calculations. Each metric is defined exactly once in this package.

The METRICS registry records every published metric id, its unit and method version.
Screens read computed.json keys; they never re-implement a formula.
"""

METRICS = {}


def metric(metric_id, unit=None, method=None, inputs=()):
    """Register a metric definition (decorator). Duplicate ids are a programming error."""
    def deco(fn):
        if metric_id in METRICS:
            raise RuntimeError(f"duplicate metric definition: {metric_id}")
        METRICS[metric_id] = {"id": metric_id, "unit": unit, "method": method or f"{metric_id}.v1",
                              "inputs": list(inputs), "fn": f"{fn.__module__}.{fn.__name__}"}
        return fn
    return deco
