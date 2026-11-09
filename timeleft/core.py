from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List

PERIODS = ("day", "week", "month", "quarter", "year")

BAR_STYLES = {
    "unicode": ("\u2588", "\u2591"),
    "ascii": ("#", "-"),
}


def _add_months(reference: date, months: int) -> datetime:
    index = reference.month - 1 + months
    return datetime(reference.year + index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Span:
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


def span_for(period: str, now: datetime, week_start: int = 0) -> Span:
    if period == "day":
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)
    elif period == "week":
        if not 0 <= week_start <= 6:
            raise ValueError("week_start must be between 0 (Monday) and 6 (Sunday)")
        start = datetime(now.year, now.month, now.day) - timedelta(
            days=(now.weekday() - week_start) % 7
        )
        end = start + timedelta(days=7)
    elif period == "month":
        start = _add_months(now, 0)
        end = _add_months(now, 1)
    elif period == "quarter":
        start = _add_months(now, -((now.month - 1) % 3))
        end = _add_months(start, 3)
    elif period == "year":
        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)
    else:
        raise ValueError(
            "unknown period %r (choose from %s)" % (period, ", ".join(PERIODS))
        )
    return Span(period, start, end)


def format_duration(seconds: float) -> str:
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


def render_bar(fraction: float, width: int = 25, style: str = "unicode") -> str:
    if width < 1:
        raise ValueError("bar width must be at least 1")
    try:
        fill, empty = BAR_STYLES[style]
    except KeyError:
        raise ValueError("unknown bar style %r" % (style,)) from None
    clamped = min(max(fraction, 0.0), 1.0)
    filled = int(clamped * width)
    return fill * filled + empty * (width - filled)


def build_report(
    periods: Iterable[str], now: datetime, week_start: int = 0
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for period in periods:
        span = span_for(period, now, week_start)
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
