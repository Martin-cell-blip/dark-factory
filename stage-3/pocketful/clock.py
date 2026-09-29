"""Server timestamps: RFC 3339 with an explicit offset, strictly increasing within one state.

Strictly increasing stamps make creation order and created_at order the same, so the
feeds can list newest first by walking their records backwards.
"""
import re
from datetime import datetime, timedelta, timezone

_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})")


def format_time(moment: datetime) -> str:
    return moment.isoformat(timespec="microseconds")


def parse_time(value) -> datetime | None:
    """An RFC 3339 timestamp with an explicit offset, or None."""
    if not isinstance(value, str) or len(value) < 20 or value[10] not in "Tt":
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def parse_instant(value) -> datetime | None:
    """A strict RFC 3339 instant: date, 'T', time with seconds, and Z or a numeric offset.
    Naive local times, bare dates and empty values are None."""
    if not isinstance(value, str) or _INSTANT.fullmatch(value) is None:
        return None
    return parse_time(value.replace("z", "Z").replace("t", "T", 1))


class Clock:
    def __init__(self) -> None:
        self.last: datetime | None = None

    def observe(self, stamp: str) -> None:
        moment = parse_time(stamp)
        if moment is not None and (self.last is None or moment > self.last):
            self.last = moment

    def now(self) -> str:
        moment = datetime.now(timezone.utc)
        if self.last is not None and moment <= self.last:
            moment = self.last.astimezone(timezone.utc) + timedelta(microseconds=1)
        self.last = moment
        return format_time(moment)
