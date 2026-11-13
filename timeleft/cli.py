from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from . import __version__
from .core import PERIODS, build_report, format_duration, render_bar, span_for

DEFAULT_WIDTH = 25
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEK_STARTS = {name: index for index, name in enumerate(WEEKDAY_NAMES)}
WEEK_STARTS.update({name[:3]: index for index, name in enumerate(WEEKDAY_NAMES)})
PERIOD_ALIASES = {period[0]: period for period in PERIODS}
RELATIVE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
CLOCK_FORMATS = ("%H:%M:%S", "%H:%M")
TWELVE_HOUR = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*([ap])\.?m\.?$", re.IGNORECASE)
RELATIVE_OFFSET = re.compile(r"^([+-])((?:\d+[smhdw])+)$", re.IGNORECASE)
RELATIVE_TOKEN = re.compile(r"(\d+)([smhdw])", re.IGNORECASE)
NATURAL_OFFSET = re.compile(
    r"^(?:(in)\s+)?(\d+|an?)\s*([a-z]+?)(?:\s+(ago))?(?:\s+from\s+now)?$",
    re.IGNORECASE,
)
NATURAL_UNITS = {
    "s": 1, "sec": 1, "second": 1,
    "m": 60, "min": 60, "minute": 60,
    "h": 3600, "hr": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
    "w": 604800, "week": 604800,
}
DAY_KEYWORDS = {"today": 0, "tomorrow": 1, "yesterday": -1}
DAY_PHRASES = {
    "day after tomorrow": 2,
    "the day after tomorrow": 2,
    "day before yesterday": -2,
    "the day before yesterday": -2,
}
NAMED_CLOCKS = {"noon": (12, 0, 0), "midnight": (0, 0, 0)}
WEEKDAY_MODIFIERS = {"next", "last", "this"}
END_KEYWORDS = {
    "end of day": "day", "eod": "day",
    "end of week": "week", "eow": "week",
    "end of month": "month", "eom": "month",
    "end of quarter": "quarter", "eoq": "quarter",
    "end of year": "year", "eoy": "year",
}


def midnight_of(base: datetime, days: int = 0) -> datetime:
    return base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)


def weekday_offset(base: datetime, text: str) -> Optional[int]:
    index = WEEK_STARTS.get(text.lower())
    if index is None:
        return None
    return (index - base.weekday()) % 7


def shift_weekday(base: datetime, name: str, modifier: str) -> int:
    index = WEEK_STARTS[name]
    if modifier == "this":
        return index - base.weekday()
    if modifier == "next":
        ahead = (index - base.weekday()) % 7
        return ahead or 7
    behind = (base.weekday() - index) % 7
    return -(behind or 7)


def parse_clock_time(text: str) -> Optional[Tuple[int, int, int]]:
    named = NAMED_CLOCKS.get(text.lower())
    if named is not None:
        return named
    twelve = TWELVE_HOUR.match(text)
    if twelve is not None:
        hour = int(twelve.group(1))
        minute = int(twelve.group(2) or 0)
        second = int(twelve.group(3) or 0)
        if not 1 <= hour <= 12 or minute > 59 or second > 59:
            return None
        hour = hour % 12 + (12 if twelve.group(4).lower() == "p" else 0)
        return (hour, minute, second)
    for pattern in CLOCK_FORMATS:
        try:
            clock = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return (clock.hour, clock.minute, clock.second)
    return None


def parse_natural_offset(text: str) -> Optional[int]:
    match = NATURAL_OFFSET.match(text)
    if match is None:
        return None
    word = match.group(3).lower()
    unit = NATURAL_UNITS.get(word) or NATURAL_UNITS.get(word.rstrip("s"))
    if unit is None:
        return None
    amount = match.group(2).lower()
    seconds = (1 if amount in ("a", "an") else int(amount)) * unit
    return -seconds if match.group(4) else seconds


def parse_moment(text: str, now: Optional[datetime] = None) -> datetime:
    value = text.strip()
    if value.lower().startswith("at "):
        value = value[3:].strip()
    base = now or datetime.now()
    offset = RELATIVE_OFFSET.match(value)
    if offset:
        seconds = sum(
            int(amount) * RELATIVE_UNITS[unit.lower()]
            for amount, unit in RELATIVE_TOKEN.findall(offset.group(2))
        )
        return base + timedelta(seconds=seconds if offset.group(1) == "+" else -seconds)
    natural = parse_natural_offset(value)
    if natural is not None:
        return base + timedelta(seconds=natural)
    keyword = value.lower()
    if keyword == "now":
        return base.replace(microsecond=0)
    if keyword in DAY_KEYWORDS:
        return midnight_of(base, DAY_KEYWORDS[keyword])
    for phrase, days in DAY_PHRASES.items():
        if keyword == phrase:
            return midnight_of(base, days)
        if keyword.startswith(phrase + " "):
            rest = value[len(phrase) :].strip()
            if rest.lower().startswith("at "):
                rest = rest[3:].strip()
            clock = parse_clock_time(rest)
            if clock is None:
                raise ValueError("expected a clock time after %r" % phrase)
            day = midnight_of(base, days)
            return day.replace(hour=clock[0], minute=clock[1], second=clock[2])
    if keyword in NAMED_CLOCKS:
        return midnight_of(base).replace(
            hour=NAMED_CLOCKS[keyword][0],
            minute=NAMED_CLOCKS[keyword][1],
            second=NAMED_CLOCKS[keyword][2],
        )
    ahead = weekday_offset(base, keyword)
    if ahead is not None:
        return midnight_of(base, ahead)
    words = value.split()
    if len(words) >= 2:
        anchor_word = next(
            (
                word
                for word in words
                if word.lower() in DAY_KEYWORDS or word.lower() in WEEK_STARTS
            ),
            None,
        )
        if anchor_word is not None:
            lowered = anchor_word.lower()
            modifiers = [
                word.lower() for word in words if word.lower() in WEEKDAY_MODIFIERS
            ]
            clock_words = [
                word
                for word in words
                if word.lower() not in (lowered, "at")
                and word.lower() not in WEEKDAY_MODIFIERS
            ]
            clock = parse_clock_time(" ".join(clock_words)) if clock_words else None
            if clock_words and clock is None:
                raise ValueError("expected a clock time next to %r" % anchor_word)
            if lowered in DAY_KEYWORDS:
                days = DAY_KEYWORDS[lowered]
            else:
                days = weekday_offset(base, lowered)
                if modifiers:
                    days = shift_weekday(base, lowered, modifiers[-1])
            day = midnight_of(base, days)
            if clock is None:
                return day
            return day.replace(hour=clock[0], minute=clock[1], second=clock[2])
    unit = value[-1:].lower()
    if len(value) > 2 and value[0] in "+-" and unit in RELATIVE_UNITS:
        raise ValueError("relative offset needs a whole number, e.g. +90m")
    clock = parse_clock_time(value)
    if clock is not None:
        return base.replace(
            hour=clock[0],
            minute=clock[1],
            second=clock[2],
            microsecond=0,
        )
    if value.endswith(("Z", "z")):
        moment = datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)
        return moment.astimezone().replace(tzinfo=None)
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def parse_target(text: str, now: datetime, week_start: int = 0) -> datetime:
    period = END_KEYWORDS.get(text.strip().lower())
    if period is not None:
        return span_for(period, now).end
    return parse_moment(text, now=now)


def supports_block_glyphs(stream) -> bool:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "\u2588".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def resolve_period(name: str) -> Optional[str]:
    lowered = name.lower()
    if lowered in PERIODS:
        return lowered
    if lowered in PERIOD_ALIASES:
        return PERIOD_ALIASES[lowered]
    if lowered.endswith("s") and lowered[:-1] in PERIODS:
        return lowered[:-1]
    return None


def format_row(row: dict, width: int, plain: bool, bar_style: str = "unicode") -> str:
    if plain:
        return "%-7s %5.1f%%  %s left" % (
            row["period"],
            row["percent"],
            row["remaining"],
        )
    bar = render_bar(row["fraction"], width, bar_style)
    return "%-7s [%s] %5.1f%%  %s left" % (
        row["period"],
        bar,
        row["percent"],
        row["remaining"],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="timeleft",
        description="Show how much of the day, week, month, quarter or year is left.",
    )
    parser.add_argument(
        "periods",
        nargs="*",
        metavar="PERIOD",
        help="one of %s, its first letter or its plural (default: all)"
        % ", ".join(PERIODS),
    )
    parser.add_argument(
        "--at",
        metavar="WHEN",
        help=(
            "ISO 8601 moment, a clock time such as 15:30, an offset such as "
            "+2h30m, one of now, today, tomorrow, yesterday, noon, midnight, "
            "a weekday name such as friday, a period end such as \"end of "
            "week\", or one of those followed by a clock time such as "
            "\"tomorrow 09:00\""
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print JSON instead of a table",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="omit the progress bar",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="draw the bar with ASCII characters (# and -)",
    )
    value_output = parser.add_mutually_exclusive_group()
    value_output.add_argument(
        "--countdown",
        action="store_true",
        help="print only the time left, one period per line",
    )
    value_output.add_argument(
        "--percent",
        action="store_true",
        help="print only the percentage, one period per line",
    )
    value_output.add_argument(
        "--elapsed",
        action="store_true",
        help="print only the time already spent, one period per line",
    )
    value_output.add_argument(
        "--until",
        metavar="WHEN",
        help=(
            "print only the time left until WHEN, in the same formats as --at "
            "plus end of day/week/month/quarter/year (eod, eow, ...)"
        ),
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        metavar="N",
        help="bar width in characters (default: %d)" % DEFAULT_WIDTH,
    )
    parser.add_argument(
        "--week-start",
        type=str.lower,
        choices=WEEK_STARTS,
        default="monday",
        metavar="DAY",
        help="first day of the week, any weekday name or its first three letters (default: monday)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="timeleft %s" % __version__,
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.width < 1:
        parser.error("--width must be at least 1")

    week_start = WEEK_STARTS[args.week_start]
    selected = args.periods or list(PERIODS)
    periods: List[str] = []
    for name in selected:
        period = resolve_period(name)
        if period is None:
            parser.error(
                "invalid period %r (choose from %s)"
                % (name, ", ".join(PERIODS + tuple(PERIOD_ALIASES)))
            )
        periods.append(period)
    if args.at:
        try:
            now = parse_target(args.at, datetime.now())
        except ValueError:
            parser.error(
                "--at could not parse %r (expected an ISO timestamp, a clock "
                "time, a day name, or an offset like +90m)" % args.at
            )
    else:
        now = datetime.now().replace(microsecond=0)

    if args.until:
        try:
            target = parse_target(args.until, now, week_start)
        except ValueError:
            parser.error(
                "--until could not parse %r (it accepts the same formats as --at)"
                % args.until
            )
        remaining = max(0.0, (target - now).total_seconds())
        if args.json:
            json.dump(
                {
                    "now": now.isoformat(),
                    "until": target.isoformat(),
                    "remaining_seconds": round(remaining),
                    "remaining": format_duration(remaining),
                },
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0
        print(format_duration(remaining))
        return 0

    rows = build_report(periods, now, week_start=week_start)

    if args.json:
        json.dump({"now": now.isoformat(), "periods": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.countdown or args.percent or args.elapsed:
        for row in rows:
            if args.countdown:
                print(row["remaining"])
            elif args.percent:
                print("%.1f%%" % row["percent"])
            else:
                print(row["elapsed"])
        return 0

    bar_style = "ascii" if args.ascii or not supports_block_glyphs(sys.stdout) else "unicode"
    for row in rows:
        print(format_row(row, args.width, args.plain, bar_style))
    return 0
