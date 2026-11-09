"""Core period arithmetic for timeleft.

Everything here works on naive local ``datetime`` objects on purpose: the tool
must stay usable without a timezone database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List

PERIODS = ("day", "week", "month", "quarter", "year")


def _month_start(reference: date) -> datetime:
    return datetime(reference.year, reference.month, 1)


def _add_months(reference: date, months: int) -> date:
    """Move ``reference`` by ``months`` keeping the day of month where possible."""
    month_index = reference.month - 1 + months
    year = reference.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _next_month_start(reference: date) -> datetime:
    first = _add_months(reference, 1)
    return datetime(first.year, first.month, 1)


def _quarter_start(reference: date) -> date:
    first_month = 3 * ((reference.month - 1) // 3) + 1
    return date(reference.year, first_month, 1)


@dataclass(frozen=True)
class Span:
    """A half-open period ``[start, end)`` with a human readable name."""

    name: str
    start: datetime
    end: datetime

    @property
    def total_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def elapsed_seconds(self, now: datetime) -> float:
        elapsed = (now - self.start).total_seconds()
        return min(max(elapsed, 0.0), self.total_seconds)

    def remaining_seconds(self, now: datetime) -> float:
        return self.total_seconds - self.elapsed_seconds(now)

    def fraction_elapsed(self, now: datetime) -> float:
        total = self.total_seconds
        return 0.0 if total <= 0 else self.elapsed_seconds(now) / total

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


def span_for(period: str, now: datetime) -> Span:
    """Return the :class:`Span` of ``period`` containing ``now``."""
    if period == "day":
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)
    elif period == "week":
        day_start = datetime(now.year, now.month, now.day)
        start = day_start - timedelta(days=now.weekday())
        end = start + timedelta(days=7)
    elif period == "month":
        start = _month_start(now)
        end = _next_month_start(now)
    elif period == "quarter":
        start_date = _quarter_start(now)
        start = datetime(start_date.year, start_date.month, 1)
        next_quarter_month = _add_months(start_date, 3)
        end = datetime(next_quarter_month.year, next_quarter_month.month, 1)
    elif period == "year":
        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)
    else:
        raise ValueError(
            "unknown period %r (choose from %s)" % (period, ", ".join(PERIODS))
        )
    return Span(period, start, end)


def format_duration(seconds: float) -> str:
    """Format a number of seconds as a compact two-part duration.

    Examples: ``0s``, ``45s``, ``3m 05s``, ``2h 07m``, ``5d 01h``.
    """
    total = max(0, int(round(seconds)))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return "%dd %02dh" % (days, hours)
    if hours:
        return "%dh %02dm" % (hours, minutes)
    if minutes:
        return "%dm %02ds" % (minutes, secs)
    return "%ds" % secs


def render_bar(fraction: float, width: int = 25) -> str:
    """Render a fixed-width progress bar for ``fraction`` in ``[0, 1]``."""
    if width < 1:
        raise ValueError("bar width must be at least 1")
    clamped = min(max(fraction, 0.0), 1.0)
    filled = int(clamped * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def build_report(periods: Iterable[str], now: datetime) -> List[Dict[str, object]]:
    """Build the data behind the text and JSON output."""
    rows: List[Dict[str, object]] = []
    for period in periods:
        span = span_for(period, now)
        fraction = span.fraction_elapsed(now)
        rows.append(
            {
                "period": period,
                "start": span.start.isoformat(),
                "end": span.end.isoformat(),
                "fraction": round(fraction, 6),
                "percent": round(fraction * 100.0, 1),
                "elapsed_seconds": round(span.elapsed_seconds(now)),
                "remaining_seconds": round(span.remaining_seconds(now)),
                "remaining": format_duration(span.remaining_seconds(now)),
            }
        )
    return rows
