"""Build context: parsed, indexed data shared by every calculation."""

import math
from collections import defaultdict
from datetime import timedelta

from agame import timeutil as tu
from agame.paths import load_config, load_exercise_library


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def stdev(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def percentile(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return xs[int(k)]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def linreg(xs, ys):
    """Least squares slope/intercept. Returns (slope, intercept) or (None, None)."""
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pts) < 2:
        return None, None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        return None, None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    slope = sxy / sxx
    return slope, my - slope * mx


def pearson(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 3:
        return None, n
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pts))
    sy = math.sqrt(sum((p[1] - my) ** 2 for p in pts))
    if sx == 0 or sy == 0:
        return None, n
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / (sx * sy), n


RUN_SPORTS = {"run", "trail_run", "treadmill_run", "track_run"}
RIDE_SPORTS = {"ride", "virtual_ride"}
SWIM_SPORTS = {"swim", "open_water_swim"}


def sport_family(sport):
    if sport in RUN_SPORTS:
        return "run"
    if sport in RIDE_SPORTS:
        return "ride"
    if sport in SWIM_SPORTS:
        return "swim"
    if sport in ("walk", "hike"):
        return "walk"
    if sport in ("strength", "hiit"):
        return "strength"
    return "other"


class Ctx:
    def __init__(self, data, build_date):
        self.data = data
        self.profile = data.get("profile", {})
        self.cfg = load_config(self.profile)
        self.library = load_exercise_library()
        locale = self.profile.get("locale") or {}
        self.tzname = locale.get("timezone") or tu.DEFAULT_TZ
        self.tz = tu.tzinfo(self.tzname)
        self.units = locale.get("units") or "metric"
        self.week_start = locale.get("week_start") or self.cfg["periods"]["week_start"]
        self.d = build_date
        self.now = tu.build_now(build_date, self.tz)
        self.fixture = self._fixture_flag()
        self._series_cache = {}
        self._daily_cache = {}
        self._prepare_workouts()
        self._prepare_sleep()
        self._prepare_covered()

    def _fixture_flag(self):
        flags = {p.get("fixture") for p in self.data.values() if isinstance(p, dict)}
        if "synthetic" in flags:
            return "synthetic"
        if flags <= {"empty", None}:
            return "empty"
        return None

    # ------------------------------------------------------------- physiology
    def phys(self, key):
        m = (self.profile.get("physiology") or {}).get(key)
        return m.get("value") if m else None

    def phys_obj(self, key):
        return (self.profile.get("physiology") or {}).get(key)

    def target(self, key):
        return (self.profile.get("targets") or {}).get(key)

    # ------------------------------------------------------------- series
    def series(self, sid):
        """Sorted list of (datetime_local or None, local_date, value, point) excluding future points."""
        if sid in self._series_cache:
            return self._series_cache[sid]
        pts = ((self.data.get("metrics") or {}).get("series") or {}).get(sid, [])
        out = []
        for p in pts:
            if "t" in p:
                dt = tu.local_dt(p["t"], self.tz)
                if dt > self.now:
                    continue
                out.append((dt, dt.date(), p["v"], p))
            else:
                dd = tu.parse_date(p["date"])
                if dd > self.d:
                    continue
                out.append((None, dd, p["v"], p))
        out.sort(key=lambda r: (r[1], r[0].isoformat() if r[0] else ""))
        self._series_cache[sid] = out
        return out

    def by_day(self, sid):
        """dict local_date -> list of (datetime, value) for timestamped points."""
        key = ("by_day", sid)
        if key in self._daily_cache:
            return self._daily_cache[key]
        out = defaultdict(list)
        for dt, dd, v, _ in self.series(sid):
            if dt is not None:
                out[dd].append((dt, v))
        self._daily_cache[key] = out
        return out

    def series_ids(self):
        return sorted(((self.data.get("metrics") or {}).get("series") or {}).keys())

    def series_meta(self, sid):
        cat = self.cfg["metrics_catalog"].get(sid)
        if cat:
            return cat
        m = ((self.data.get("metrics") or {}).get("series_meta") or {}).get(sid)
        return m or {"label": sid, "unit": "", "agg": "mean"}

    def daily(self, sid, agg=None):
        """dict local_date -> aggregated value."""
        key = (sid, agg)
        if key in self._daily_cache:
            return self._daily_cache[key]
        agg = agg or self.series_meta(sid).get("agg", "mean")
        groups = defaultdict(list)
        for _, dd, v, _ in self.series(sid):
            groups[dd].append(v)
        out = {}
        for dd, vs in groups.items():
            if agg == "sum":
                out[dd] = sum(vs)
            elif agg == "last":
                out[dd] = vs[-1]
            elif agg == "max":
                out[dd] = max(vs)
            elif agg == "min":
                out[dd] = min(vs)
            else:
                out[dd] = sum(vs) / len(vs)
        self._daily_cache[key] = out
        return out

    def series_as_of(self, sid):
        s = self.series(sid)
        if not s:
            return None
        last = s[-1]
        if last[0] is not None:
            return last[0].isoformat()
        return tu.end_of_day(last[1], self.tz).replace(hour=23, minute=59).isoformat()

    # ------------------------------------------------------------- workouts
    def _prepare_workouts(self):
        ann = {a["workout_id"]: a for a in (self.data.get("load") or {}).get("annotations", [])}
        self.annotations = ann
        out = []
        for w in (self.data.get("workouts") or {}).get("workouts", []):
            s = tu.local_dt(w["start"], self.tz)
            if s > self.now:
                continue
            e = tu.local_dt(w["end"], self.tz)
            ww = dict(w)
            ww["_start"], ww["_end"], ww["_date"] = s, e, s.date()
            ww["_dur"] = w.get("duration_s") or (e - s).total_seconds()
            ww["_family"] = sport_family(w["sport"])
            ww["_ann"] = ann.get(w["source_id"])
            out.append(ww)
        out.sort(key=lambda w: (w["_start"], w["source_id"]))
        self.workouts = out
        self.workouts_by_id = {w["source_id"]: w for w in out}
        self.workouts_by_day = defaultdict(list)
        for w in out:
            self.workouts_by_day[w["_date"]].append(w)

    # ------------------------------------------------------------- sleep
    def _prepare_sleep(self):
        nights = []
        for n in (self.data.get("sleep") or {}).get("nights", []):
            e = tu.local_dt(n["end"], self.tz)
            if e > self.now:
                continue
            s = tu.local_dt(n["start"], self.tz)
            nn = dict(n)
            nn["_start"], nn["_end"] = s, e
            nn["_date"] = tu.parse_date(n["date"]) if n.get("date") else e.date()
            nights.append(nn)
        nights.sort(key=lambda n: (n["_end"], n["source_id"]))
        self.nights = nights

    # ------------------------------------------------------------- coverage
    def _prepare_covered(self):
        cov = set()
        for sid in self.series_ids():
            for _, dd, _, _ in self.series(sid):
                cov.add(dd)
        for w in self.workouts:
            cov.add(w["_date"])
        for n in self.nights:
            cov.add(n["_date"])
            cov.add(n["_date"] - timedelta(days=1))
        self.covered = cov
        self.first_day = min(cov) if cov else None

    # ------------------------------------------------------------- formatting
    def local_iso(self, dt):
        return dt.astimezone(self.tz).isoformat() if dt else None

    def exercise(self, ex_id):
        for x in (self.data.get("strength") or {}).get("exercises", []):
            if x["id"] == ex_id:
                return x
        for x in self.library["exercises"]:
            if x["id"] == ex_id:
                return x
        return None

    def status_on(self, d):
        """User/source-set activity status covering date d (latest start wins)."""
        best = None
        for s in (self.data.get("journal") or {}).get("status", []):
            st, en = tu.parse_date(s["start"]), tu.parse_date(s.get("end")) if s.get("end") else None
            if st <= d and (en is None or d <= en):
                if best is None or st >= tu.parse_date(best["start"]):
                    best = s
        return best
