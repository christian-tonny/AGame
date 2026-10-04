"""Timezone-aware time and period helpers. All local dates use profile timezone."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Africa/Kigali"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def tzinfo(name):
    return ZoneInfo(name or DEFAULT_TZ)


def parse_ts(value):
    """Parse ISO-8601 timestamp with offset. Naive timestamps are rejected."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without UTC offset: {value!r}")
    return dt


class AmbiguousTime(ValueError):
    pass


def localize(value, tzname):
    """ISO timestamp with offset. A wall-clock time ("YYYY-MM-DD HH:MM:SS" or ISO without offset) is placed in tzname.
    Wall times that fall in a DST gap or overlap are refused rather than guessed."""
    if value is None:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s.replace(" ", "T", 1) if len(s) > 10 and s[10] == " " else s)
    if dt.tzinfo is not None:
        return dt.isoformat()
    if not tzname:
        raise ValueError(f"timestamp {value!r} has no UTC offset and no timezone was given")
    tz = tzinfo(tzname)
    a, b = dt.replace(tzinfo=tz, fold=0), dt.replace(tzinfo=tz, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise AmbiguousTime(f"{value!r} is ambiguous or does not exist in {tzname} (daylight-saving change); send it with an offset")
    return a.isoformat()


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(dt):
    return None if dt is None else dt.isoformat()


def local_date(ts, tz):
    return parse_ts(ts).astimezone(tz).date()


def local_dt(ts, tz):
    return parse_ts(ts).astimezone(tz)


def day_bounds(d, tz):
    start = datetime.combine(d, time(0, 0), tzinfo=tz)
    return start, start + timedelta(days=1)


def end_of_day(d, tz):
    return datetime.combine(d, time(23, 59, 59), tzinfo=tz)


def daterange(start, end_inclusive):
    d = start
    while d <= end_inclusive:
        yield d
        d += timedelta(days=1)


def week_start(d, week_start_name="monday"):
    idx = WEEKDAYS.index(week_start_name)
    return d - timedelta(days=(d.weekday() - idx) % 7)


def period_bounds(d, kind, week_start_name="monday"):
    """Return (start, end_inclusive) of the period containing d."""
    if kind == "day":
        return d, d
    if kind == "week":
        s = week_start(d, week_start_name)
        return s, s + timedelta(days=6)
    if kind == "month":
        s = d.replace(day=1)
        nxt = (s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1))
        return s, nxt - timedelta(days=1)
    if kind == "quarter":
        qm = 3 * ((d.month - 1) // 3) + 1
        s = d.replace(month=qm, day=1)
        em = qm + 3
        nxt = s.replace(year=s.year + 1, month=em - 12) if em > 12 else s.replace(month=em)
        return s, nxt - timedelta(days=1)
    if kind == "year":
        return d.replace(month=1, day=1), d.replace(month=12, day=31)
    raise ValueError(kind)


def previous_period(start, end, kind, week_start_name="monday"):
    prev_end = start - timedelta(days=1)
    return period_bounds(prev_end, kind, week_start_name)


def same_period_last_year(start, end):
    def shift(d):
        try:
            return d.replace(year=d.year - 1)
        except ValueError:  # Feb 29
            return d.replace(year=d.year - 1, day=28)
    return shift(start), shift(end)


def period_key(d, kind, week_start_name="monday"):
    s, _ = period_bounds(d, kind, week_start_name)
    if kind == "quarter":
        return f"{s.year}-Q{(s.month - 1) // 3 + 1}"
    if kind == "year":
        return str(s.year)
    if kind == "month":
        return f"{s.year}-{s.month:02d}"
    return s.isoformat()


def minutes_of_day(dt):
    return dt.hour * 60 + dt.minute + dt.second / 60.0


def build_now(build_date, tz):
    """Deterministic 'now' for a build: end of the build date in profile tz."""
    return end_of_day(build_date, tz)


def to_utc(dt):
    return dt.astimezone(timezone.utc)
