from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from . import __version__
from .core import PERIODS, build_report, render_bar

DEFAULT_WIDTH = 25
WEEK_STARTS = {"monday": 0, "sunday": 6}
PERIOD_ALIASES = {period[0]: period for period in PERIODS}
RELATIVE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
CLOCK_FORMATS = ("%H:%M:%S", "%H:%M")


def parse_moment(text: str, now: Optional[datetime] = None) -> datetime:
    value = text.strip()
    base = now or datetime.now()
    unit = value[-1:].lower()
    if len(value) > 2 and value[0] in "+-" and unit in RELATIVE_UNITS:
        if not value[1:-1].isdigit():
            raise ValueError("relative offset needs a whole number, e.g. +90m")
        seconds = int(value[1:-1]) * RELATIVE_UNITS[unit]
        return base + timedelta(seconds=seconds if value[0] == "+" else -seconds)
    if ":" in value:
        for pattern in CLOCK_FORMATS:
            try:
                clock = datetime.strptime(value, pattern)
            except ValueError:
                continue
            return base.replace(
                hour=clock.hour,
                minute=clock.minute,
                second=clock.second,
                microsecond=0,
            )
    if value.endswith("Z"):
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
        help="one of %s or its first letter (default: all)" % ", ".join(PERIODS),
    )
    parser.add_argument(
        "--at",
        metavar="WHEN",
        help="ISO 8601 moment, a clock time such as 15:30, or an offset such as +90m",
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
        help="first day of the week, monday or sunday (default: monday)",
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
    unknown = [name for name in selected if name not in PERIOD_ALIASES and name not in PERIODS]
    if unknown:
        parser.error(
            "invalid period %r (choose from %s)"
            % (unknown[0], ", ".join(PERIODS + tuple(PERIOD_ALIASES)))
        )
    periods: List[str] = [PERIOD_ALIASES.get(name, name) for name in selected]
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
