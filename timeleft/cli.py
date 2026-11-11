from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from . import __version__
from .core import PERIODS, build_report, render_bar

DEFAULT_WIDTH = 25
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEK_STARTS = {name: index for index, name in enumerate(WEEKDAY_NAMES)}
WEEK_STARTS.update({name[:3]: index for index, name in enumerate(WEEKDAY_NAMES)})
PERIOD_ALIASES = {period[0]: period for period in PERIODS}
RELATIVE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
CLOCK_FORMATS = ("%H:%M:%S", "%H:%M")
RELATIVE_OFFSET = re.compile(r"^([+-])((?:\d+[smhdw])+)$", re.IGNORECASE)
RELATIVE_TOKEN = re.compile(r"(\d+)([smhdw])", re.IGNORECASE)
DAY_KEYWORDS = {"today": 0, "tomorrow": 1, "yesterday": -1}
NAMED_CLOCKS = {"noon": (12, 0, 0), "midnight": (0, 0, 0)}


def midnight_of(base: datetime, days: int = 0) -> datetime:
    return base.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)


def parse_clock_time(text: str) -> Optional[Tuple[int, int, int]]:
    named = NAMED_CLOCKS.get(text.lower())
    if named is not None:
        return named
    for pattern in CLOCK_FORMATS:
        try:
            clock = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return (clock.hour, clock.minute, clock.second)
    return None


def parse_moment(text: str, now: Optional[datetime] = None) -> datetime:
    value = text.strip()
    base = now or datetime.now()
    offset = RELATIVE_OFFSET.match(value)
    if offset:
        seconds = sum(
            int(amount) * RELATIVE_UNITS[unit.lower()]
            for amount, unit in RELATIVE_TOKEN.findall(offset.group(2))
        )
        return base + timedelta(seconds=seconds if offset.group(1) == "+" else -seconds)
    keyword = value.lower()
    if keyword == "now":
        return base.replace(microsecond=0)
    if keyword in DAY_KEYWORDS:
        return midnight_of(base, DAY_KEYWORDS[keyword])
    if keyword in NAMED_CLOCKS:
        return midnight_of(base).replace(
            hour=NAMED_CLOCKS[keyword][0],
            minute=NAMED_CLOCKS[keyword][1],
            second=NAMED_CLOCKS[keyword][2],
        )
    words = value.split()
    if len(words) == 2:
        keyword_word = next(
            (word for word in words if word.lower() in DAY_KEYWORDS), None
        )
        if keyword_word is not None:
            clock = parse_clock_time(words[1] if words[0] == keyword_word else words[0])
            if clock is None:
                raise ValueError("expected a clock time next to %r" % keyword_word)
            day = midnight_of(base, DAY_KEYWORDS[keyword_word.lower()])
            return day.replace(hour=clock[0], minute=clock[1], second=clock[2])
    unit = value[-1:].lower()
    if len(value) > 2 and value[0] in "+-" and unit in RELATIVE_UNITS:
        raise ValueError("relative offset needs a whole number, e.g. +90m")
    if ":" in value:
        clock = parse_clock_time(value)
        if clock is not None:
            return base.replace(
                hour=clock[0],
                minute=clock[1],
                second=clock[2],
                microsecond=0,
            )
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


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
            "or a day keyword followed by a clock time such as "
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
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        metavar="N",
        help="bar width in characters (default: %d)" % DEFAULT_WIDTH,
    )
    parser.add_argument(
        "--week-start",
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
            now = parse_moment(args.at)
        except ValueError:
            parser.error("--at expects an ISO 8601 timestamp or an offset like +90m")
    else:
        now = datetime.now().replace(microsecond=0)

    rows = build_report(periods, now, week_start=WEEK_STARTS[args.week_start])

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
