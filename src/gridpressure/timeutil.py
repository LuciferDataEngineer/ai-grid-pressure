"""NEM market time helpers.

AEMO publishes settlement timestamps in NEM time: Australian Eastern
Standard Time (UTC+10) all year, with no daylight-saving shift.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def parse_nem_timestamp(value: str) -> datetime:
    """Parse an AEMO timestamp. ``24:00:00`` is the next midnight."""
    text = value.strip().strip('"')
    if " " not in text:
        raise ValueError(f"Not a NEM timestamp: {value}")
    day, clock = text.split(" ", 1)
    if clock.startswith("24:"):
        parsed = datetime.strptime(day, "%Y/%m/%d") + timedelta(days=1)
        rest = clock[2:]  # starts with the colon after 24, or :MM:SS
        if rest != ":00:00":
            parsed = datetime.strptime(f"{parsed:%Y/%m/%d} 00{rest}", "%Y/%m/%d %H:%M:%S")
        return parsed
    return datetime.strptime(text, "%Y/%m/%d %H:%M:%S")


def market_date(interval_end: datetime):
    """Trading date for an interval-ending timestamp.

    The interval ending at midnight belongs to the previous calendar date.
    """
    if interval_end.hour == 0 and interval_end.minute == 0 and interval_end.second == 0:
        return (interval_end - timedelta(days=1)).date()
    return interval_end.date()


def hour_of_day(interval_end: datetime) -> int:
    """Clock hour of the interval start, 0–23, in NEM time."""
    return (interval_end - timedelta(minutes=5)).hour


def format_nem(moment: datetime) -> str:
    hour = moment.hour
    suffix = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return (
        f"{moment.day} {moment.strftime('%b')} {moment.year}, "
        f"{hour12}:{moment.minute:02d}{suffix} NEM time"
    )


def format_date(value) -> str:
    return f"{value.day} {value.strftime('%b')} {value.year}"
