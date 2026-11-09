from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List, Optional, Sequence

from . import __version__
from .core import PERIODS, build_report, render_bar

DEFAULT_WIDTH = 25


def parse_moment(text: str) -> datetime:
    value = text.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def format_row(row: dict, width: int, plain: bool) -> str:
    if plain:
        return "%-7s %5.1f%%  %s left" % (
            row["period"],
            row["percent"],
            row["remaining"],
        )
    bar = render_bar(row["fraction"], width)
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
        choices=PERIODS,
        metavar="PERIOD",
        help="one of %s (default: all)" % ", ".join(PERIODS),
    )
    parser.add_argument(
        "--at",
        metavar="ISO8601",
        help="evaluate at a fixed moment instead of now",
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
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        metavar="N",
        help="bar width in characters (default: %d)" % DEFAULT_WIDTH,
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

    periods: List[str] = args.periods or list(PERIODS)
    if args.at:
        try:
            now = parse_moment(args.at)
        except ValueError:
            parser.error("--at expects an ISO 8601 timestamp")
    else:
        now = datetime.now().replace(microsecond=0)

    rows = build_report(periods, now)

    if args.json:
        json.dump({"now": now.isoformat(), "periods": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    for row in rows:
        print(format_row(row, args.width, args.plain))
    return 0
