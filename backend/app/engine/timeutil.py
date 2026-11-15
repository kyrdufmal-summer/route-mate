from __future__ import annotations

from datetime import datetime, time, timedelta


def parse_hhmm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def at_clock(day: datetime, hhmm: str) -> datetime:
    """'24:00' 은 다음날 00:00 으로 해석한다."""
    h, m = parse_hhmm(hhmm)
    base = datetime.combine(day.date(), time(0, 0))
    return base + timedelta(hours=h, minutes=m)


def is_open_through(day: datetime, open_hhmm: str, close_hhmm: str, start: datetime, end: datetime) -> bool:
    if open_hhmm == "00:00" and close_hhmm == "24:00":
        return True
    return at_clock(day, open_hhmm) <= start and end <= at_clock(day, close_hhmm)


def minutes_between(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")
