from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from . import __version__
from .core import ALL_PERIODS, PERIODS, build_report, format_duration, render_bar, span_for

DEFAULT_WIDTH = 25
MAX_WATCH_SECONDS = 86400
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEK_STARTS = {name: index for index, name in enumerate(WEEKDAY_NAMES)}
WEEK_STARTS.update({name[:3]: index for index, name in enumerate(WEEKDAY_NAMES)})
PERIOD_ALIASES = {period[0]: period for period in ALL_PERIODS}
RELATIVE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
CLOCK_FORMATS = ("%H:%M:%S", "%H:%M")
TWELVE_HOUR = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*([ap])\.?m\.?$", re.IGNORECASE)
CLOCK_PHRASE = re.compile(
    r"^(half|(?:a\s+)?quarter)\s+(past|to)\s+(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?m?\.?$",
    re.IGNORECASE,
)
CLOCK_PHRASE_NAMED = re.compile(
    r"^(half|(?:a\s+)?quarter)\s+(past|to)\s+(noon|midday|midnight)$", re.IGNORECASE
)
RELATIVE_OFFSET = re.compile(r"^([+-])((?:\d+(?:\.\d+)?[smhdw])+)$", re.IGNORECASE)
RELATIVE_TOKEN = re.compile(r"(\d+(?:\.\d+)?)([smhdw])", re.IGNORECASE)
NATURAL_PART = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*([a-z]+)|(an?|one)\s+([a-z]+))", re.IGNORECASE
)
NATURAL_PHRASES = (
    (
        re.compile(
            r"\b(\d+(?:\.\d+)?)\s+and\s+a\s+half\s+(hours?|minutes?|days?|weeks?|fortnights?)\b",
            re.IGNORECASE,
        ),
        r"\1.5 \2",
    ),
    (
        re.compile(
            r"\b(?:an?|one)\s+and\s+a\s+half\s+(hours?|minutes?|days?|weeks?|fortnights?)\b",
            re.IGNORECASE,
        ),
        r"1.5 \1",
    ),
    (
        re.compile(
            r"\b(?:an?|one)\s+(hours?|minutes?|days?|weeks?|fortnights?)\s+and\s+a\s+half\b",
            re.IGNORECASE,
        ),
        r"1.5 \1",
    ),
    (
        re.compile(
            r"\b(?:an?\s+)?half\s+(?:an?\s+)?(hours?|minutes?|days?|weeks?|fortnights?)\b",
            re.IGNORECASE,
        ),
        r"0.5 \1",
    ),
    (re.compile(r"\ban hour and a half\b", re.IGNORECASE), "90 minutes"),
    (re.compile(r"\b(?:one|1)\s+hours?\s+and\s+a\s+half\b", re.IGNORECASE), "90 minutes"),
    (re.compile(r"\b(?:one|1)\s+and\s+a\s+half\s+hours?\b", re.IGNORECASE), "90 minutes"),
    (re.compile(r"\bthree quarters of an hour\b", re.IGNORECASE), "45 minutes"),
    (re.compile(r"\b(?:a )?quarter of an hour\b", re.IGNORECASE), "15 minutes"),
    (re.compile(r"\bhalf an hour\b", re.IGNORECASE), "30 minutes"),
    (re.compile(r"\ba half hour\b", re.IGNORECASE), "30 minutes"),
    (re.compile(r"\bhalf a day\b", re.IGNORECASE), "12 hours"),
)
NATURAL_FILLER = re.compile(r"^(?:\s*(?:,|and)?\s*)*$", re.IGNORECASE)
NATURAL_TAIL = re.compile(r"^[\s,]*$")
NATURAL_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
    "fortnight": 1209600, "fortnights": 1209600,
}
DAY_KEYWORDS = {"today": 0, "tomorrow": 1, "yesterday": -1}
DAY_PHRASES = {
    "day after tomorrow": 2,
    "the day after tomorrow": 2,
    "day before yesterday": -2,
    "the day before yesterday": -2,
}
NAMED_CLOCKS = {"noon": (12, 0, 0), "midday": (12, 0, 0), "midnight": (0, 0, 0)}
WEEKDAY_MODIFIERS = {"next", "last", "this"}
END_KEYWORDS = {
    "end of day": "day", "eod": "day",
    "end of week": "week", "eow": "week",
    "end of month": "month", "eom": "month",
    "end of quarter": "quarter", "eoq": "quarter",
    "end of year": "year", "eoy": "year",
    "end of hour": "hour", "eoh": "hour",
}
START_KEYWORDS = {"start of %s" % period: period for period in ALL_PERIODS}
START_KEYWORDS.update({"so%s" % period[0]: period for period in ALL_PERIODS})
SHIFTED_PERIOD = re.compile(
    r"^(?:(start|end) of )?(next|last|this) (hour|day|week|month|quarter|year)$"
)


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


def clock_phrase(text: str) -> Optional[Tuple[int, int, int]]:
    match = CLOCK_PHRASE.match(text)
    if match is not None:
        amount = 30 if match.group(1).lower() == "half" else 15
        delta = -amount if match.group(2).lower() == "to" else amount
        hour = int(match.group(3))
        minute = int(match.group(4) or 0)
        marker = match.group(5)
        if not 1 <= hour <= 12 or minute > 59:
            return None
        if marker is not None:
            hour = hour % 12 + (12 if marker.lower() == "p" else 0)
        total = (hour * 60 + minute + delta) % (24 * 60)
        return (total // 60, total % 60, 0)
    match = CLOCK_PHRASE_NAMED.match(text)
    if match is None:
        return None
    amount = 30 if match.group(1).lower() == "half" else 15
    delta = -amount if match.group(2).lower() == "to" else amount
    hour, minute, second = NAMED_CLOCKS[match.group(3).lower()]
    total = (hour * 60 + minute + delta) % (24 * 60)
    return (total // 60, total % 60, second)


def parse_clock_time(text: str) -> Optional[Tuple[int, int, int]]:
    named = NAMED_CLOCKS.get(text.lower())
    if named is not None:
        return named
    phrase = clock_phrase(text)
    if phrase is not None:
        return phrase
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
    value = text.strip().lower()
    sign = 1
    starts_ahead = value.startswith("in ") or value.endswith(" from now")
    if value.startswith("in "):
        value = value[3:].strip()
    if value.endswith(" from now"):
        value = value[: -len(" from now")].strip()
    if value.endswith(" ago"):
        value = value[: -len(" ago")].strip()
        sign = -1
    if starts_ahead and sign < 0:
        return None
    for pattern, replacement in NATURAL_PHRASES:
        value = pattern.sub(replacement, value)
    total = 0.0
    parts = 0
    end = 0
    for match in NATURAL_PART.finditer(value):
        if not NATURAL_FILLER.match(value[end : match.start()]):
            return None
        word = (match.group(2) or match.group(4)).lower()
        unit = NATURAL_UNITS.get(word)
        if unit is None:
            return None
        amount = match.group(1)
        total += (1.0 if amount is None else float(amount)) * unit
        parts += 1
        end = match.end()
    if not parts or not NATURAL_TAIL.match(value[end:]):
        return None
    return sign * round(total)


CALENDAR_TOKEN = re.compile(
    r"(\d+)\s*(months?|years?)|(an?|one)\s+(months?|years?)", re.IGNORECASE
)


def parse_calendar_offset(text: str) -> Optional[int]:
    value = text.strip().lower()
    sign = 1
    starts_ahead = value.startswith("in ") or value.endswith(" from now")
    if value.startswith("in "):
        value = value[3:].strip()
    if value.endswith(" from now"):
        value = value[: -len(" from now")].strip()
    if value.endswith(" ago"):
        value = value[: -len(" ago")].strip()
        sign = -1
    if starts_ahead and sign < 0:
        return None
    months = 0
    found = 0
    end = 0
    for match in CALENDAR_TOKEN.finditer(value):
        if not NATURAL_FILLER.match(value[end : match.start()]):
            return None
        amount = 1 if match.group(1) is None else int(match.group(1))
        unit = (match.group(2) or match.group(4)).lower()
        months += amount * (1 if unit.startswith("month") else 12)
        found += 1
        end = match.end()
    if not found or not NATURAL_TAIL.match(value[end:]):
        return None
    return sign * months


def shift_months(moment: datetime, months: int) -> datetime:
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def parse_moment(text: str, now: Optional[datetime] = None) -> datetime:
    value = text.strip()
    if value.lower().startswith("at "):
        value = value[3:].strip()
    base = now or datetime.now()
    offset = RELATIVE_OFFSET.match(value)
    if offset:
        seconds = sum(
            float(amount) * RELATIVE_UNITS[unit.lower()]
            for amount, unit in RELATIVE_TOKEN.findall(offset.group(2))
        )
        moment = base + timedelta(seconds=seconds if offset.group(1) == "+" else -seconds)
        return moment.replace(microsecond=0)
    natural = parse_natural_offset(value)
    if natural is not None:
        return (base + timedelta(seconds=natural)).replace(microsecond=0)
    calendar_offset = parse_calendar_offset(value)
    if calendar_offset is not None:
        return shift_months(base, calendar_offset).replace(microsecond=0)
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
        raise ValueError("relative offset needs a number directly followed by a unit, e.g. +90m")
    clock = parse_clock_time(value)
    if clock is not None:
        return base.replace(
            hour=clock[0],
            minute=clock[1],
            second=clock[2],
            microsecond=0,
        )
    partial = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if partial is not None:
        year, month, day = (int(part) for part in partial.groups())
        return datetime(year, month, day)
    partial = re.match(r"^(\d{4})(?:-(\d{1,2}))?$", value)
    if partial is not None:
        year = int(partial.group(1))
        month = int(partial.group(2) or 1)
        if not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")
        return datetime(year, month, 1)
    if value.endswith(("Z", "z")):
        moment = datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)
        return moment.astimezone().replace(tzinfo=None)
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def target_phrase(text: str) -> str:
    phrase = text.strip().lower()
    if phrase.startswith("the "):
        phrase = phrase[4:]
    return re.sub(r"\bof the\b", "of", phrase)


def shifted_period_target(
    phrase: str, now: datetime, week_start: int
) -> Optional[datetime]:
    match = SHIFTED_PERIOD.match(phrase)
    if match is None:
        return None
    boundary, modifier, period = match.groups()
    span = span_for(period, now, week_start)
    if modifier == "next":
        span = span_for(period, span.end, week_start)
    elif modifier == "last":
        span = span_for(period, span.start - timedelta(seconds=1), week_start)
    return span.end if boundary == "end" else span.start


def parse_target(text: str, now: datetime, week_start: int = 0) -> datetime:
    phrase = target_phrase(text)
    shifted = shifted_period_target(phrase, now, week_start)
    if shifted is not None:
        return shifted
    period = END_KEYWORDS.get(phrase)
    if period is not None:
        return span_for(period, now, week_start).end
    period = START_KEYWORDS.get(phrase)
    if period is not None:
        return span_for(period, now, week_start).start
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
    if lowered in ALL_PERIODS:
        return lowered
    if lowered in PERIOD_ALIASES:
        return PERIOD_ALIASES[lowered]
    if lowered.endswith("s") and lowered[:-1] in ALL_PERIODS:
        return lowered[:-1]
    return None


def format_row(
    row: dict, width: int, plain: bool, bar_style: str = "unicode", precision: int = 1
) -> str:
    percent = "%.*f%%" % (precision, row["percent"])
    if plain:
        return "%-7s %*s  %s left" % (
            row["period"],
            precision + 5,
            percent,
            row["remaining"],
        )
    bar = render_bar(row["fraction"], width, bar_style)
    return "%-7s [%s] %*s  %s left" % (
        row["period"],
        bar,
        precision + 5,
        percent,
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
        help="one of %s, its first letter or its plural (default: %s)"
        % (", ".join(ALL_PERIODS), ", ".join(PERIODS)),
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
        "-j",
        "--json",
        action="store_true",
        help="print JSON instead of a table",
    )
    parser.add_argument(
        "-p",
        "--plain",
        action="store_true",
        help="omit the progress bar",
    )
    parser.add_argument(
        "-a",
        "--ascii",
        action="store_true",
        help="draw the bar with ASCII characters (# and -)",
    )
    value_output = parser.add_mutually_exclusive_group()
    value_output.add_argument(
        "-c",
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
        "--percent-left",
        action="store_true",
        help="print only the percentage still ahead, one period per line",
    )
    value_output.add_argument(
        "-e",
        "--elapsed",
        action="store_true",
        help="print only the time already spent, one period per line",
    )
    value_output.add_argument(
        "--total",
        action="store_true",
        help="print only the total length of each period, one period per line",
    )
    value_output.add_argument(
        "--until",
        metavar="WHEN",
        help=(
            "print only the time left until WHEN, in the same formats as --at "
            "plus end of day/week/month/quarter/year (eod, eow, ...)"
        ),
    )
    value_output.add_argument(
        "--since",
        metavar="WHEN",
        help=(
            "print only the time elapsed since WHEN, in the same formats as "
            "--until"
        ),
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=1,
        metavar="N",
        help="decimal places in percentages, 0 to 6 (default: 1)",
    )
    parser.add_argument(
        "-w",
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
        "--watch",
        type=float,
        metavar="SECONDS",
        help="redraw every SECONDS until interrupted",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="timeleft %s" % __version__,
    )
    return parser


def emit_report(
    args: argparse.Namespace,
    periods: List[str],
    week_start: int,
    now: datetime,
    parser: argparse.ArgumentParser,
) -> int:
    if args.since:
        try:
            target = parse_target(args.since, now, week_start)
        except ValueError:
            parser.error(
                "--since could not parse %r (it accepts the same formats as --at)"
                % args.since
            )
        elapsed = max(0.0, (now - target).total_seconds())
        if args.json:
            json.dump(
                {
                    "now": now.isoformat(),
                    "since": target.isoformat(),
                    "elapsed_seconds": round(elapsed),
                    "elapsed": format_duration(elapsed),
                },
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
            return 0
        print(format_duration(elapsed))
        return 0

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

    rows = build_report(
        periods, now, week_start=week_start, precision=args.precision
    )

    if args.json:
        json.dump({"now": now.isoformat(), "periods": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.countdown or args.percent or args.percent_left or args.elapsed or args.total:
        for row in rows:
            if args.countdown:
                print(row["remaining"])
            elif args.percent:
                print("%.*f%%" % (args.precision, row["percent"]))
            elif args.percent_left:
                print("%.*f%%" % (args.precision, 100.0 - row["percent"]))
            elif args.total:
                print(row["total"])
            else:
                print(row["elapsed"])
        return 0

    bar_style = "ascii" if args.ascii or not supports_block_glyphs(sys.stdout) else "unicode"
    for row in rows:
        print(
            format_row(
                row, args.width, args.plain, bar_style, precision=args.precision
            )
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.width < 1:
        parser.error("--width must be at least 1")
    if not 0 <= args.precision <= 6:
        parser.error("--precision must be between 0 and 6")
    if args.watch is not None:
        if not math.isfinite(args.watch) or args.watch <= 0:
            parser.error("--watch must be a positive number of seconds")
        if args.watch > MAX_WATCH_SECONDS:
            parser.error("--watch must be at most %d seconds" % MAX_WATCH_SECONDS)
    if args.watch is not None and args.json:
        parser.error("--watch cannot be combined with --json")

    week_start = WEEK_STARTS[args.week_start]
    selected = args.periods or list(PERIODS)
    periods: List[str] = []
    for group in selected:
        for name in group.split(","):
            name = name.strip()
            period = resolve_period(name) if name else None
            if period is None:
                parser.error(
                    "invalid period %r (choose from %s)"
                    % (name, ", ".join(ALL_PERIODS + tuple(PERIOD_ALIASES)))
                )
            if period not in periods:
                periods.append(period)

    anchor = None
    if args.at:
        try:
            anchor = parse_target(args.at, datetime.now(), week_start)
        except ValueError:
            parser.error(
                "--at could not parse %r (expected an ISO timestamp, a clock "
                "time, a day name, or an offset like +90m)" % args.at
            )

    def current_moment() -> datetime:
        return anchor if anchor is not None else datetime.now().replace(microsecond=0)

    try:
        if args.watch is not None:
            try:
                while True:
                    if not args.json and sys.stdout.isatty():
                        sys.stdout.write("\033[H\033[J")
                    emit_report(args, periods, week_start, current_moment(), parser)
                    sys.stdout.flush()
                    time.sleep(args.watch)
            except KeyboardInterrupt:
                return 0

        return emit_report(args, periods, week_start, current_moment(), parser)
    except BrokenPipeError:
        silence_broken_pipe()
        return 0


def silence_broken_pipe() -> None:
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError):
        pass
