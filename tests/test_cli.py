import io
import json
import os
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from timeleft.cli import (
    ANSI_GREEN,
    ANSI_RED,
    ANSI_YELLOW,
    auto_width,
    color_code,
    format_row,
    main,
    parse_moment,
    parse_target,
    supports_block_glyphs,
)


def run_cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class ParseMomentTest(unittest.TestCase):
    def test_plain_iso(self):
        self.assertEqual(parse_moment("2026-11-09T12:00"), datetime(2026, 11, 9, 12, 0))

    def test_date_only(self):
        self.assertEqual(parse_moment("2026-11-09"), datetime(2026, 11, 9))

    def test_iso_week_dates(self):
        self.assertEqual(parse_moment("2026-W46-1"), datetime(2026, 11, 9))
        self.assertEqual(parse_moment("2026-w46-7"), datetime(2026, 11, 15))
        self.assertEqual(parse_moment("2026-W46"), datetime(2026, 11, 9))

    def test_iso_week_dates_reject_bad_weeks(self):
        for text in ("2026-W54", "2026-W00", "2026-W46-8"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text)

    def test_unpadded_iso_dates(self):
        self.assertEqual(parse_moment("2026-1-9"), datetime(2026, 1, 9))
        self.assertEqual(parse_moment("2026-11-9"), datetime(2026, 11, 9))
        self.assertEqual(parse_moment("2026-1-19"), datetime(2026, 1, 19))

    def test_unpadded_iso_dates_reject_impossible_days(self):
        for text in ("2026-2-30", "2026-13-1", "2026-0-9"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text)

    def test_month_precision_iso_is_the_first_of_the_month(self):
        self.assertEqual(parse_moment("2026-11"), datetime(2026, 11, 1))
        self.assertEqual(parse_moment("2026-3"), datetime(2026, 3, 1))

    def test_year_precision_iso_is_the_first_of_the_year(self):
        self.assertEqual(parse_moment("2026"), datetime(2026, 1, 1))

    def test_month_precision_iso_rejects_bad_months(self):
        with self.assertRaises(ValueError):
            parse_moment("2026-13")

    def test_z_suffix_becomes_local_naive(self):
        moment = parse_moment("2026-11-09T12:00:00Z")
        self.assertIsNone(moment.tzinfo)
        expected = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).astimezone()
        self.assertEqual(moment, expected.replace(tzinfo=None))

    def test_date_only_with_z_suffix_is_utc_midnight(self):
        expected = datetime(2026, 11, 9, tzinfo=timezone.utc).astimezone()
        self.assertEqual(parse_moment("2026-11-09Z"), expected.replace(tzinfo=None))
        self.assertEqual(parse_moment("2026-11-09z"), expected.replace(tzinfo=None))

    def test_lowercase_z_suffix_is_utc_too(self):
        self.assertEqual(
            parse_moment("2026-11-09T12:00:00z"),
            parse_moment("2026-11-09T12:00:00Z"),
        )

    def test_iso_accepts_a_space_between_date_and_time(self):
        self.assertEqual(parse_moment("2026-11-09 12:00"), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(
            parse_moment("2026-11-09 12:00:30"), datetime(2026, 11, 9, 12, 0, 30)
        )
        self.assertEqual(parse_moment("2026-11-09 9:30"), datetime(2026, 11, 9, 9, 30))
        self.assertEqual(parse_moment("2026-11-09 9"), datetime(2026, 11, 9, 9, 0))

    def test_iso_space_form_also_converts_utc(self):
        self.assertIsNone(parse_moment("2026-11-09 12:00:00Z").tzinfo)
        self.assertEqual(
            parse_moment("2026-11-09 12:00:00Z"),
            parse_moment("2026-11-09T12:00:00Z"),
        )

    def test_compact_iso_dates(self):
        self.assertEqual(parse_moment("20261109"), datetime(2026, 11, 9))
        self.assertEqual(parse_moment("202611"), datetime(2026, 11, 1))

    def test_compact_iso_datetimes(self):
        self.assertEqual(parse_moment("20261109T12"), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(parse_moment("20261109T1200"), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(
            parse_moment("20261109T120030"), datetime(2026, 11, 9, 12, 0, 30)
        )

    def test_compact_iso_utc_converts_like_the_extended_form(self):
        self.assertEqual(
            parse_moment("20261109T120000Z"), parse_moment("2026-11-09T12:00:00Z")
        )

    def test_compact_iso_rejects_impossible_fields(self):
        for text in ("20261309", "20260230", "20261109T2500"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text)

    def test_month_name_dates(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "dec 25": datetime(2026, 12, 25),
            "25 december": datetime(2026, 12, 25),
            "december the 25th": datetime(2026, 12, 25),
            "25th of Dec 2027": datetime(2027, 12, 25),
            "december 25 2027": datetime(2027, 12, 25),
            "1 may": datetime(2027, 5, 1),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_month_name_dates_roll_into_the_next_year(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("jan 5", now=base), datetime(2027, 1, 5))
        self.assertEqual(parse_moment("nov 10", now=base), datetime(2026, 11, 10))

    def test_month_name_date_that_is_today_stays_today(self):
        base = datetime(2026, 12, 25, 8, 0)
        self.assertEqual(parse_moment("dec 25", now=base), datetime(2026, 12, 25))
        self.assertEqual(parse_moment("december 25 at 9am", now=base), datetime(2026, 12, 25, 9, 0))

    def test_month_name_dates_take_a_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(
            parse_moment("dec 25 at 9am", now=base), datetime(2026, 12, 25, 9, 0)
        )

    def test_month_name_dates_reject_a_missing_day(self):
        with self.assertRaises(ValueError):
            parse_moment("feb 30", now=datetime(2026, 11, 9, 12, 0))

    def test_ordinal_day_of_the_month(self):
        base = datetime(2026, 11, 21, 12, 0)
        cases = {
            "the 25th": datetime(2026, 11, 25),
            "22nd": datetime(2026, 11, 22),
            "21st": datetime(2026, 11, 21),
            "1st": datetime(2026, 12, 1),
            "the 31st": datetime(2026, 12, 31),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_ordinal_day_rejects_impossible_days(self):
        with self.assertRaises(ValueError):
            parse_moment("32nd", now=datetime(2026, 11, 21, 12, 0))

    def test_ordinal_day_of_a_shifted_month(self):
        base = datetime(2026, 11, 21, 12, 0)
        cases = {
            "the 25th of next month": datetime(2026, 12, 25),
            "1st of last month": datetime(2026, 10, 1),
            "the 21st of this month": datetime(2026, 11, 21),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_ordinal_day_of_a_shifted_month_rejects_short_months(self):
        with self.assertRaises(ValueError):
            parse_moment("31st of next month", now=datetime(2026, 1, 21, 12, 0))

    def test_iso_offset_without_a_colon(self):
        self.assertEqual(
            parse_moment("2026-11-09T12:00+0200"),
            parse_moment("2026-11-09T12:00+02:00"),
        )
        self.assertEqual(
            parse_moment("2026-11-09T12:00:30-0530"),
            parse_moment("2026-11-09T12:00:30-05:30"),
        )

    def test_iso_offset_with_hours_only(self):
        self.assertEqual(
            parse_moment("2026-11-09T12:00-05"),
            parse_moment("2026-11-09T12:00-05:00"),
        )

    def test_offset_is_converted(self):
        moment = parse_moment("2026-11-09T12:00:00+02:00")
        self.assertIsNone(moment.tzinfo)
        expected = datetime(2026, 11, 9, 12, 0, tzinfo=timezone(timedelta(hours=2))).astimezone()
        self.assertEqual(moment, expected.replace(tzinfo=None))

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_moment("yesterday-ish")

    def test_relative_offsets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "+90m": datetime(2026, 11, 9, 13, 30),
            "-2h": datetime(2026, 11, 9, 10, 0),
            "+30s": datetime(2026, 11, 9, 12, 0, 30),
            "+1d": datetime(2026, 11, 10, 12, 0),
            "+1w": datetime(2026, 11, 16, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_relative_offset_drops_sub_second_precision(self):
        base = datetime(2026, 11, 9, 12, 0, 0, 123456)
        self.assertEqual(parse_moment("+90m", now=base), datetime(2026, 11, 9, 13, 30))
        self.assertEqual(parse_moment("in 2 hours", now=base), datetime(2026, 11, 9, 14, 0))

    def test_relative_offset_accepts_uppercase_unit(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("+2H", now=base), datetime(2026, 11, 9, 14, 0))

    def test_relative_offsets_can_be_combined(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "+2h30m": datetime(2026, 11, 9, 14, 30),
            "+1d12h": datetime(2026, 11, 11, 0, 0),
            "-1w2d": datetime(2026, 10, 31, 12, 0),
            "+1H30M": datetime(2026, 11, 9, 13, 30),
            "+2h 30m": datetime(2026, 11, 9, 14, 30),
            "-1w 2d": datetime(2026, 10, 31, 12, 0),
            "+1d 12h 30m": datetime(2026, 11, 11, 0, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_relative_offsets_accept_fractions(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "+1.5h": datetime(2026, 11, 9, 13, 30),
            "-0.5h": datetime(2026, 11, 9, 11, 30),
            "+1.5h15m": datetime(2026, 11, 9, 13, 45),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_relative_offset_needs_number_and_unit(self):
        with self.assertRaises(ValueError):
            parse_moment("+1.5 h", now=datetime(2026, 11, 9, 12, 0))

    def test_relative_offset_with_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_moment("+90x", now=datetime(2026, 11, 9, 12, 0))

    def test_signed_calendar_offsets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "+2mo": datetime(2027, 1, 9, 12, 0),
            "-1y": datetime(2025, 11, 9, 12, 0),
            "+1month": datetime(2026, 12, 9, 12, 0),
            "+1month 2mo": datetime(2027, 2, 9, 12, 0),
            "-2 months": datetime(2026, 9, 9, 12, 0),
            "+1y 2mo 3d": datetime(2028, 1, 12, 12, 0),
            "+1mo 90m": datetime(2026, 12, 9, 13, 30),
            "+0mo": datetime(2026, 11, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_signed_calendar_offsets_clamp_the_day(self):
        base = datetime(2026, 1, 31, 12, 0)
        self.assertEqual(parse_moment("+1mo", now=base), datetime(2026, 2, 28, 12, 0))
        leap = datetime(2024, 1, 31, 12, 0)
        self.assertEqual(parse_moment("+1mo", now=leap), datetime(2024, 2, 29, 12, 0))

    def test_signed_calendar_offsets_reject_fractions(self):
        with self.assertRaises(ValueError):
            parse_moment("+1.5mo", now=datetime(2026, 11, 9, 12, 0))

    def test_natural_offsets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in 2 hours": datetime(2026, 11, 9, 14, 0),
            "in 90 minutes": datetime(2026, 11, 9, 13, 30),
            "in 1 day": datetime(2026, 11, 10, 12, 0),
            "in 2 weeks": datetime(2026, 11, 23, 12, 0),
            "30 sec": datetime(2026, 11, 9, 12, 0, 30),
            "2h ago": datetime(2026, 11, 9, 10, 0),
            "90 minutes ago": datetime(2026, 11, 9, 10, 30),
            "In 3 Hours": datetime(2026, 11, 9, 15, 0),
            "2 hours from now": datetime(2026, 11, 9, 14, 0),
            "5 days from now": datetime(2026, 11, 14, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_calendar_offsets(self):
        base = datetime(2026, 11, 9, 12, 0, 0, 500000)
        cases = {
            "in 2 months": datetime(2027, 1, 9, 12, 0),
            "in 1 year": datetime(2027, 11, 9, 12, 0),
            "3 years ago": datetime(2023, 11, 9, 12, 0),
            "1 year 2 months from now": datetime(2028, 1, 9, 12, 0),
            "in 18 months": datetime(2028, 5, 9, 12, 0),
            "2 months": datetime(2027, 1, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_calendar_offsets_accept_a_an_and_one(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in a month": datetime(2026, 12, 9, 12, 0),
            "a year ago": datetime(2025, 11, 9, 12, 0),
            "one year 2 months": datetime(2028, 1, 9, 12, 0),
            "in an hour": datetime(2026, 11, 9, 13, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_calendar_offsets_understand_quarters(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in a quarter": datetime(2027, 2, 9, 12, 0),
            "in 2 quarters": datetime(2027, 5, 9, 12, 0),
            "a quarter ago": datetime(2026, 8, 9, 12, 0),
            "two quarters from now": datetime(2027, 5, 9, 12, 0),
            "1 year 2 quarters": datetime(2028, 5, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_signed_calendar_offsets_understand_quarters(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "+1 quarter": datetime(2027, 2, 9, 12, 0),
            "-1q": datetime(2026, 8, 9, 12, 0),
            "+1qtr": datetime(2027, 2, 9, 12, 0),
            "+1y 2 quarters": datetime(2028, 5, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_calendar_offsets_clamp_the_day(self):
        base = datetime(2024, 1, 31, 9, 0)
        self.assertEqual(parse_moment("in 1 month", now=base), datetime(2024, 2, 29, 9, 0))

    def test_calendar_offsets_reject_contradictions(self):
        with self.assertRaises(ValueError):
            parse_moment("in 2 months ago", now=datetime(2026, 11, 9, 12, 0))

    def test_natural_offsets_accept_fractions(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in 1.5 hours": datetime(2026, 11, 9, 13, 30),
            "in 0.5h": datetime(2026, 11, 9, 12, 30),
            "2.5 days ago": datetime(2026, 11, 7),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_a_and_an_as_one(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in an hour": datetime(2026, 11, 9, 13, 0),
            "in a minute": datetime(2026, 11, 9, 12, 1),
            "a week ago": datetime(2026, 11, 2, 12, 0),
            "an hour from now": datetime(2026, 11, 9, 13, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_one_and_a_half(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in one hour": datetime(2026, 11, 9, 13, 0),
            "in one minute": datetime(2026, 11, 9, 12, 1),
            "one week ago": datetime(2026, 11, 2, 12, 0),
            "in a half hour": datetime(2026, 11, 9, 12, 30),
            "in 1 hour and a half": datetime(2026, 11, 9, 13, 30),
            "in one hour and a half": datetime(2026, 11, 9, 13, 30),
            "in one and a half hours": datetime(2026, 11, 9, 13, 30),
            "in half an hour": datetime(2026, 11, 9, 12, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_half_amounts_of_other_units(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in a week and a half": datetime(2026, 11, 20, 0, 0),
            "in 2 and a half weeks": datetime(2026, 11, 27, 0, 0),
            "in 2 days and a half": datetime(2026, 11, 12, 0, 0),
            "a day and a half ago": datetime(2026, 11, 8, 0, 0),
            "2 weeks and a half ago": datetime(2026, 10, 23, 0, 0),
            "half a week": datetime(2026, 11, 13, 0, 0),
            "half a day ago": datetime(2026, 11, 9, 0, 0),
            "1.5 days ago": datetime(2026, 11, 8, 0, 0),
            "in a fortnight and a half": datetime(2026, 11, 30, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_spelled_numbers(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in two hours": datetime(2026, 11, 9, 14, 0),
            "three days ago": datetime(2026, 11, 6, 12, 0),
            "in twenty five minutes": datetime(2026, 11, 9, 12, 25),
            "in twenty-five minutes": datetime(2026, 11, 9, 12, 25),
            "two weeks and a half ago": datetime(2026, 10, 23, 0, 0),
            "in three quarters of an hour": datetime(2026, 11, 9, 12, 45),
            "in one month": datetime(2026, 12, 9, 12, 0),
            "in two months": datetime(2027, 1, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_couple_and_few(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in a couple of hours": datetime(2026, 11, 9, 14, 0),
            "a couple days ago": datetime(2026, 11, 7, 12, 0),
            "in a couple fortnights": datetime(2026, 12, 7, 12, 0),
            "in a few minutes": datetime(2026, 11, 9, 12, 3),
            "a few weeks ago": datetime(2026, 10, 19, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_multiple_parts(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in 1 hour 30 minutes": datetime(2026, 11, 9, 13, 30),
            "in 2 days and 3 hours": datetime(2026, 11, 11, 15, 0),
            "in 90 minutes 30 seconds": datetime(2026, 11, 9, 13, 30, 30),
            "in 1.5 hours 15 minutes": datetime(2026, 11, 9, 13, 45),
            "1 day 2 hours ago": datetime(2026, 11, 8, 10, 0),
            "2 hours from now": datetime(2026, 11, 9, 14, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_accept_half_and_quarter_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in half an hour": datetime(2026, 11, 9, 12, 30),
            "half an hour ago": datetime(2026, 11, 9, 11, 30),
            "in a quarter of an hour": datetime(2026, 11, 9, 12, 15),
            "in three quarters of an hour": datetime(2026, 11, 9, 12, 45),
            "in an hour and a half": datetime(2026, 11, 9, 13, 30),
            "in half a day": datetime(2026, 11, 10, 0, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_natural_offsets_reject_unknown_units(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in (
            "in 2 ms",
            "in 2 hourss",
            "in 3 minuts",
            "in 4 dayss",
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)

    def test_natural_offsets_reject_in_and_ago_together(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in ("in 2 hours ago", "2 hours from now ago"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)

    def test_natural_offsets_reject_trailing_junk(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in ("in 2 hours later", "in 2 hours and", "2 hours ago ago"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)

    def test_natural_offset_with_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_moment("in 2 moons", now=datetime(2026, 11, 9, 12, 0))

    def test_natural_offsets_accept_fortnights(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in a fortnight": datetime(2026, 11, 23, 12, 0),
            "2 fortnights ago": datetime(2026, 10, 12, 12, 0),
            "in one fortnight": datetime(2026, 11, 23, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_clock_time_uses_today(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("15:30", now=base), datetime(2026, 11, 9, 15, 30))
        self.assertEqual(parse_moment("9:30", now=base), datetime(2026, 11, 9, 9, 30))
        self.assertEqual(
            parse_moment("15:30:45", now=base), datetime(2026, 11, 9, 15, 30, 45)
        )

    def test_bare_hour_clock_times(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("9", now=base), datetime(2026, 11, 9, 9, 0))
        self.assertEqual(parse_moment("0", now=base), datetime(2026, 11, 9, 0, 0))
        self.assertEqual(parse_moment("00", now=base), datetime(2026, 11, 9, 0, 0))
        self.assertEqual(parse_moment("23", now=base), datetime(2026, 11, 9, 23, 0))
        self.assertEqual(
            parse_moment("tomorrow at 9", now=base), datetime(2026, 11, 10, 9, 0)
        )
        self.assertEqual(parse_moment("friday 17", now=base), datetime(2026, 11, 13, 17, 0))
        with self.assertRaises(ValueError):
            parse_moment("24", now=base)

    def test_clock_time_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            parse_moment("25:00", now=datetime(2026, 11, 9, 12, 0))

    def test_dotted_clock_times(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("18.30", now=base), datetime(2026, 11, 9, 18, 30))
        self.assertEqual(parse_moment("6.30pm", now=base), datetime(2026, 11, 9, 18, 30))
        self.assertEqual(
            parse_moment("tomorrow 8.45", now=base), datetime(2026, 11, 10, 8, 45)
        )

    def test_twelve_hour_clock_times(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "9am": datetime(2026, 11, 9, 9, 0),
            "9:30pm": datetime(2026, 11, 9, 21, 30),
            "12am": datetime(2026, 11, 9, 0, 0),
            "12:15PM": datetime(2026, 11, 9, 12, 15),
            "6:30 pm": datetime(2026, 11, 9, 18, 30),
            "11:59:30 a.m.": datetime(2026, 11, 9, 11, 59, 30),
            "9:30p": datetime(2026, 11, 9, 21, 30),
            "5a": datetime(2026, 11, 9, 5, 0),
            "12:05a": datetime(2026, 11, 9, 0, 5),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_oclock_clock_times(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "5 o'clock": datetime(2026, 11, 9, 5, 0),
            "5 oclock": datetime(2026, 11, 9, 5, 0),
            "5 o clock": datetime(2026, 11, 9, 5, 0),
            "5 o'clock pm": datetime(2026, 11, 9, 17, 0),
            "12 o'clock": datetime(2026, 11, 9, 12, 0),
            "12 o'clock am": datetime(2026, 11, 9, 0, 0),
            "tomorrow 9 o'clock": datetime(2026, 11, 10, 9, 0),
            "at 7 o'clock": datetime(2026, 11, 9, 7, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_oclock_rejects_bad_hours(self):
        for text in ("0 o'clock", "13 o'clock", "5 o'clock pm am"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=datetime(2026, 11, 9, 12, 0))

    def test_twelve_hour_clock_time_with_day_anchor(self):
        base = datetime(2026, 11, 11, 12, 0)
        self.assertEqual(parse_moment("tomorrow 9am", now=base), datetime(2026, 11, 12, 9, 0))
        self.assertEqual(parse_moment("9pm friday", now=base), datetime(2026, 11, 13, 21, 0))
        self.assertEqual(parse_moment("tomorrow 9:30p", now=base), datetime(2026, 11, 12, 21, 30))

    def test_twelve_hour_clock_time_rejects_bad_values(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in ("0am", "13pm", "9:60am", "9xm"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)

    def test_day_keywords(self):
        base = datetime(2026, 11, 9, 18, 25, 40, 123456)
        self.assertEqual(parse_moment("now", now=base), datetime(2026, 11, 9, 18, 25, 40))
        self.assertEqual(parse_moment("today", now=base), datetime(2026, 11, 9))
        self.assertEqual(parse_moment("Tomorrow", now=base), datetime(2026, 11, 10))
        self.assertEqual(parse_moment("yesterday", now=base), datetime(2026, 11, 8))

    def test_day_parts_default_to_a_fixed_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "morning": datetime(2026, 11, 9, 9, 0),
            "this morning": datetime(2026, 11, 9, 9, 0),
            "afternoon": datetime(2026, 11, 9, 15, 0),
            "evening": datetime(2026, 11, 9, 19, 0),
            "night": datetime(2026, 11, 9, 22, 0),
            "tonight": datetime(2026, 11, 9, 21, 0),
            "tomorrow morning": datetime(2026, 11, 10, 9, 0),
            "tomorrow afternoon": datetime(2026, 11, 10, 15, 0),
            "yesterday evening": datetime(2026, 11, 8, 19, 0),
            "friday night": datetime(2026, 11, 13, 22, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_day_parts_take_precedence_over_a_following_clock(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(
            parse_moment("tomorrow morning at 7", now=base),
            datetime(2026, 11, 10, 7, 0),
        )
        self.assertEqual(
            parse_moment("morning at 6:30", now=base),
            datetime(2026, 11, 9, 6, 30),
        )

    def test_day_parts_reject_a_second_clock(self):
        base = datetime(2026, 11, 9, 12, 0)
        with self.assertRaises(ValueError):
            parse_moment("tomorrow morning noon", now=base)

    def test_day_keyword_with_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "tomorrow 09:00": datetime(2026, 11, 10, 9, 0),
            "yesterday 18:30": datetime(2026, 11, 8, 18, 30),
            "today 15:30:45": datetime(2026, 11, 9, 15, 30, 45),
            "Tomorrow 9:30": datetime(2026, 11, 10, 9, 30),
            "09:00 tomorrow": datetime(2026, 11, 10, 9, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_multi_word_clock_time_with_day_anchor(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "tomorrow 9:30 pm": datetime(2026, 11, 10, 21, 30),
            "9:30 pm tomorrow": datetime(2026, 11, 10, 21, 30),
            "friday 11:45 pm": datetime(2026, 11, 13, 23, 45),
            "sunday 11:59:30 a.m.": datetime(2026, 11, 15, 11, 59, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_end_of_period_targets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "end of day": datetime(2026, 11, 10),
            "eod": datetime(2026, 11, 10),
            "end of week": datetime(2026, 11, 16),
            "eow": datetime(2026, 11, 16),
            "end of month": datetime(2026, 12, 1),
            "eom": datetime(2026, 12, 1),
            "end of quarter": datetime(2027, 1, 1),
            "eoq": datetime(2027, 1, 1),
            "end of year": datetime(2027, 1, 1),
            "eoy": datetime(2027, 1, 1),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_end_of_week_honours_week_start(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("end of week", base, week_start=6), datetime(2026, 11, 15))
        self.assertEqual(parse_target("eow", base, week_start=0), datetime(2026, 11, 16))

    def test_first_and_last_day_phrases(self):
        base = datetime(2026, 11, 21, 12, 0)
        self.assertEqual(parse_target("last day of the month", base), datetime(2026, 12, 1))
        self.assertEqual(parse_target("first day of the month", base), datetime(2026, 11, 1))
        self.assertEqual(parse_target("last day of the week", base), datetime(2026, 11, 23))
        self.assertEqual(
            parse_target("first day of the week", base, week_start=6), datetime(2026, 11, 15)
        )

    def test_start_of_period_targets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "start of day": datetime(2026, 11, 9),
            "sod": datetime(2026, 11, 9),
            "start of week": datetime(2026, 11, 9),
            "sow": datetime(2026, 11, 9),
            "start of month": datetime(2026, 11, 1),
            "som": datetime(2026, 11, 1),
            "start of quarter": datetime(2026, 10, 1),
            "soq": datetime(2026, 10, 1),
            "start of year": datetime(2026, 1, 1),
            "soy": datetime(2026, 1, 1),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_start_of_week_honours_week_start(self):
        base = datetime(2026, 11, 11, 12, 0)
        self.assertEqual(parse_target("start of week", base, week_start=6), datetime(2026, 11, 8))
        self.assertEqual(parse_target("sow", base, week_start=3), datetime(2026, 11, 5))

    def test_first_and_last_day_of_shifted_periods(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "first day of next month": datetime(2026, 12, 1),
            "last day of next month": datetime(2027, 1, 1),
            "first day of last week": datetime(2026, 11, 2),
            "last day of last week": datetime(2026, 11, 9),
            "first day of this quarter": datetime(2026, 10, 1),
            "last day of next year": datetime(2028, 1, 1),
            "first day of next hour": datetime(2026, 11, 9, 13, 0),
            "the first day of the next month": datetime(2026, 12, 1),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_first_and_last_day_of_shifted_periods_accepts_a_clock(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(
            parse_target("first day of next month at 9am", base),
            datetime(2026, 12, 1, 9, 0),
        )

    def test_shifted_period_targets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "this week": datetime(2026, 11, 9),
            "next week": datetime(2026, 11, 16),
            "last week": datetime(2026, 11, 2),
            "this month": datetime(2026, 11, 1),
            "next month": datetime(2026, 12, 1),
            "last month": datetime(2026, 10, 1),
            "next quarter": datetime(2027, 1, 1),
            "last quarter": datetime(2026, 7, 1),
            "this year": datetime(2026, 1, 1),
            "next year": datetime(2027, 1, 1),
            "last year": datetime(2025, 1, 1),
            "next hour": datetime(2026, 11, 9, 13, 0),
            "last day": datetime(2026, 11, 8),
            "start of next month": datetime(2026, 12, 1),
            "end of next week": datetime(2026, 11, 23),
            "end of last month": datetime(2026, 11, 1),
            "the next year": datetime(2027, 1, 1),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_shifted_period_targets_honour_week_start(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("next week", base, week_start=6), datetime(2026, 11, 15))
        self.assertEqual(parse_target("last week", base, week_start=6), datetime(2026, 11, 1))

    def test_middle_of_period_targets(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "middle of hour": datetime(2026, 11, 9, 12, 30),
            "middle of day": datetime(2026, 11, 9, 12, 0),
            "middle of the day": datetime(2026, 11, 9, 12, 0),
            "middle of this day": datetime(2026, 11, 9, 12, 0),
            "middle of this week": datetime(2026, 11, 12, 12, 0),
            "middle of week": datetime(2026, 11, 12, 12, 0),
            "middle of month": datetime(2026, 11, 16),
            "middle of quarter": datetime(2026, 11, 16),
            "middle of year": datetime(2026, 7, 2, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_middle_of_week_honours_week_start(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(
            parse_target("middle of week", base, week_start=6), datetime(2026, 11, 11, 12, 0)
        )

    def test_middle_of_next_and_last_periods(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "middle of next week": datetime(2026, 11, 19, 12, 0),
            "middle of last week": datetime(2026, 11, 5, 12, 0),
            "middle of next month": datetime(2026, 12, 16, 12, 0),
            "middle of last year": datetime(2025, 7, 2, 12, 0),
            "middle of this day": datetime(2026, 11, 11, 12, 0),
            "middle of the next quarter": datetime(2027, 2, 15, 0, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_boundaries_accept_a_clock_time_after_at(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "end of week at 5pm": datetime(2026, 11, 16, 17, 0),
            "start of day at 9:30": datetime(2026, 11, 9, 9, 30),
            "middle of day at 3pm": datetime(2026, 11, 9, 15, 0),
            "eod at noon": datetime(2026, 11, 10, 12, 0),
            "tomorrow at 09:00": datetime(2026, 11, 10, 9, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_day_relative_boundaries(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "start of today": datetime(2026, 11, 9),
            "end of today": datetime(2026, 11, 10),
            "middle of today": datetime(2026, 11, 9, 12, 0),
            "start of tomorrow": datetime(2026, 11, 10),
            "end of tomorrow": datetime(2026, 11, 11),
            "middle of yesterday": datetime(2026, 11, 8, 12, 0),
            "end of the day after tomorrow": datetime(2026, 11, 12),
            "start of the day before yesterday": datetime(2026, 11, 7),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_target(text, base), expected)

    def test_day_relative_boundaries_take_a_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(
            parse_target("end of today at 5pm", base), datetime(2026, 11, 10, 17, 0)
        )

    def test_articles_are_ignored_in_month_name_dates(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("the 25th of december", base), datetime(2026, 12, 25))
        self.assertEqual(parse_target("the 1st of january 2027", base), datetime(2027, 1, 1))

    def test_at_accepts_middle_of_a_period(self):
        code, out = run_cli("--at", "2026-11-09T00:00", "--until", "middle of day")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "12h 00m")

    def test_target_phrases_ignore_articles(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("the end of the week", base), datetime(2026, 11, 16))
        self.assertEqual(parse_target("start of the month", base), datetime(2026, 11, 1))

    def test_end_of_period_falls_back_to_a_moment(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("tomorrow", base), datetime(2026, 11, 10))
        self.assertEqual(parse_target("+2h", base), datetime(2026, 11, 9, 14, 0))

    def test_at_connector_before_a_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "tomorrow at 09:00": datetime(2026, 11, 10, 9, 0),
            "next friday at 5pm": datetime(2026, 11, 13, 17, 0),
            "at 18:30": datetime(2026, 11, 9, 18, 30),
            "at noon": datetime(2026, 11, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_day_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "day after tomorrow": datetime(2026, 11, 11),
            "the day after tomorrow": datetime(2026, 11, 11),
            "day before yesterday": datetime(2026, 11, 7),
            "the day before yesterday": datetime(2026, 11, 7),
            "day after tomorrow 9am": datetime(2026, 11, 11, 9, 0),
            "the day before yesterday at 18:30": datetime(2026, 11, 7, 18, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_named_clock_times(self):
        base = datetime(2026, 11, 9, 18, 25, 40, 123456)
        self.assertEqual(parse_moment("noon", now=base), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(parse_moment("Midnight", now=base), datetime(2026, 11, 9))
        self.assertEqual(parse_moment("midday", now=base), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(
            parse_moment("tomorrow midday", now=base), datetime(2026, 11, 10, 12, 0)
        )
        self.assertEqual(
            parse_moment("Tomorrow noon", now=base), datetime(2026, 11, 10, 12, 0)
        )
        self.assertEqual(
            parse_moment("midnight tomorrow", now=base), datetime(2026, 11, 10)
        )

    def test_half_and_quarter_past_clock_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "half past 3": datetime(2026, 11, 9, 3, 30),
            "half past 3pm": datetime(2026, 11, 9, 15, 30),
            "quarter past 4": datetime(2026, 11, 9, 4, 15),
            "a quarter past 4pm": datetime(2026, 11, 9, 16, 15),
            "half past midnight": datetime(2026, 11, 9, 0, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_quarter_to_clock_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "quarter to 5": datetime(2026, 11, 9, 4, 45),
            "quarter to 5pm": datetime(2026, 11, 9, 16, 45),
            "a quarter to 12am": datetime(2026, 11, 9, 23, 45),
            "quarter to 12pm": datetime(2026, 11, 9, 11, 45),
            "quarter to noon": datetime(2026, 11, 9, 11, 45),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_clock_phrases_combine_with_day_anchors(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "tomorrow half past 3": datetime(2026, 11, 12, 3, 30),
            "quarter to 5pm friday": datetime(2026, 11, 13, 16, 45),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_offsets_combine_with_a_clock_time(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "in 2 days at 09:00": datetime(2026, 11, 11, 9, 0),
            "in 3 hours at half past four": datetime(2026, 11, 9, 4, 30),
            "2 days from now at five o'clock": datetime(2026, 11, 11, 5, 0),
            "2 days ago at 7pm": datetime(2026, 11, 7, 19, 0),
            "in 1 month at noon": datetime(2026, 12, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_minutes_to_clock_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "10 to 5": datetime(2026, 11, 9, 4, 50),
            "20 to 5pm": datetime(2026, 11, 9, 16, 40),
            "10 to 12am": datetime(2026, 11, 9, 23, 50),
            "10 to 12pm": datetime(2026, 11, 9, 11, 50),
            "tomorrow 10 to 5": datetime(2026, 11, 10, 4, 50),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_spelled_out_clock_phrases(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "ten to five": datetime(2026, 11, 9, 4, 50),
            "ten to midnight": datetime(2026, 11, 9, 23, 50),
            "twenty past four": datetime(2026, 11, 9, 4, 20),
            "quarter past nine": datetime(2026, 11, 9, 9, 15),
            "a quarter to nine": datetime(2026, 11, 9, 8, 45),
            "half past seven": datetime(2026, 11, 9, 7, 30),
            "seven o'clock pm": datetime(2026, 11, 9, 19, 0),
            "eleven am": datetime(2026, 11, 9, 11, 0),
            "nine pm": datetime(2026, 11, 9, 21, 0),
            "twenty to noon": datetime(2026, 11, 9, 11, 40),
            "twenty-five to five": datetime(2026, 11, 9, 4, 35),
            "twenty five to five": datetime(2026, 11, 9, 4, 35),
            "twenty five past four": datetime(2026, 11, 9, 4, 25),
            "five past nine": datetime(2026, 11, 9, 9, 5),
            "tomorrow ten to five": datetime(2026, 11, 10, 4, 50),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_clock_phrases_reject_bad_values(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in ("half past 13", "quarter to 0", "half past 3:75"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)

    def test_weekday_means_its_next_occurrence(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "friday": datetime(2026, 11, 13),
            "Wednesday": datetime(2026, 11, 11),
            "monday": datetime(2026, 11, 16),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_weekday_with_clock_time(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "friday noon": datetime(2026, 11, 13, 12, 0),
            "sat 18:00": datetime(2026, 11, 14, 18, 0),
            "18:00 monday": datetime(2026, 11, 16, 18, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_next_and_last_weekday(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "next friday": datetime(2026, 11, 13),
            "last friday": datetime(2026, 11, 6),
            "next wednesday": datetime(2026, 11, 18),
            "last wednesday": datetime(2026, 11, 4),
            "Next Monday": datetime(2026, 11, 16),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_long_weekday_abbreviations(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "tues": datetime(2026, 11, 17),
            "weds": datetime(2026, 11, 11),
            "next weds": datetime(2026, 11, 18),
            "thur": datetime(2026, 11, 12),
            "thurs 9am": datetime(2026, 11, 12, 9, 0),
            "next tues": datetime(2026, 11, 17),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_this_weekday(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "this friday": datetime(2026, 11, 13),
            "this wednesday": datetime(2026, 11, 11),
            "this monday noon": datetime(2026, 11, 9, 12, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_next_and_last_weekday_with_clock_time(self):
        base = datetime(2026, 11, 11, 12, 0)
        cases = {
            "next friday 9am": datetime(2026, 11, 13, 9, 0),
            "last monday noon": datetime(2026, 11, 9, 12, 0),
            "next friday 6:30 pm": datetime(2026, 11, 13, 18, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_day_keyword_with_bad_clock_time_raises(self):
        base = datetime(2026, 11, 9, 12, 0)
        for text in ("tomorrow 25:00", "tomorrow 9:00-ish"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_moment(text, now=base)


class SupportsBlockGlyphsTest(unittest.TestCase):
    def test_utf8_capable_stream(self):
        self.assertTrue(supports_block_glyphs(io.StringIO()))

    def test_ascii_only_stream(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="ascii")
        self.assertFalse(supports_block_glyphs(stream))


class FormatRowTest(unittest.TestCase):
    ROW = {
        "period": "day",
        "fraction": 0.5,
        "percent": 50.0,
        "remaining": "12h 00m",
    }

    def test_plain_row(self):
        line = format_row(self.ROW, 10, plain=True)
        self.assertIn("50.0%", line)
        self.assertIn("12h 00m left", line)
        self.assertNotIn("[", line)

    def test_bar_row(self):
        line = format_row(self.ROW, 10, plain=False)
        self.assertIn("[" + "\u2588" * 5 + "\u2591" * 5 + "]", line)

    def test_ascii_bar_row(self):
        line = format_row(self.ROW, 10, plain=False, bar_style="ascii")
        self.assertIn("[#####-----]", line)


class ColorTest(unittest.TestCase):
    ROW = {
        "period": "day",
        "fraction": 0.5,
        "percent": 50.0,
        "remaining": "12h 00m",
    }

    def test_color_codes_follow_the_elapsed_share(self):
        self.assertEqual(color_code(0.0), ANSI_GREEN)
        self.assertEqual(color_code(49.9), ANSI_GREEN)
        self.assertEqual(color_code(50.0), ANSI_YELLOW)
        self.assertEqual(color_code(79.9), ANSI_YELLOW)
        self.assertEqual(color_code(80.0), ANSI_RED)
        self.assertEqual(color_code(100.0), ANSI_RED)

    def test_row_colors_the_bar_and_the_percentage(self):
        line = format_row(self.ROW, 4, plain=False, color=True)
        self.assertEqual(
            line,
            "day     [\033[33m\u2588\u2588\u2591\u2591\033[0m] "
            "\033[33m 50.0%\033[0m  12h 00m left",
        )

    def test_plain_row_colors_only_the_percentage(self):
        line = format_row(self.ROW, 25, plain=True, color=True)
        self.assertEqual(
            line, "day     \033[33m 50.0%\033[0m  12h 00m left"
        )

    def test_color_always_emits_escapes_off_a_terminal(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--color", "always", "day")
        self.assertEqual(code, 0)
        self.assertIn("\033[", out)

    def test_color_never_stays_plain(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--color", "never", "day")
        self.assertEqual(code, 0)
        self.assertNotIn("\033[", out)

    def test_color_auto_is_off_off_a_terminal(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--color", "auto", "day")
        self.assertEqual(code, 0)
        self.assertNotIn("\033[", out)

    def test_color_auto_honours_no_color_and_dumb_terminals(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        def run_with(env):
            stream = Tty()
            with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(stream):
                code = main(["--at", "2026-11-09T12:00", "day"])
            return code, stream.getvalue()

        code, output = run_with({"TERM": "xterm"})
        self.assertEqual(code, 0)
        self.assertIn("\033[", output)
        self.assertNotIn("\033[", run_with({"TERM": "dumb"})[1])
        self.assertNotIn("\033[", run_with({"TERM": "xterm", "NO_COLOR": "1"})[1])

    def test_bad_color_choice_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--color", "sometimes", "day")
        self.assertEqual(caught.exception.code, 2)


class InvalidPeriodTest(unittest.TestCase):
    def test_error_lists_aliases_next_to_their_period(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), redirect_stderr(err):
            main(["frog"])
        message = err.getvalue()
        self.assertIn("hour (h, hr, hrs)", message)
        self.assertIn("day (d)", message)
        self.assertIn("month (m, mo, mos)", message)
        self.assertIn("year (y, yr, yrs)", message)


class AutoWidthTest(unittest.TestCase):
    def test_auto_width_reserves_columns_for_the_row(self):
        self.assertEqual(auto_width(80, 1), 48)
        self.assertEqual(auto_width(80, 6), 43)
        self.assertEqual(auto_width(20, 1), 1)

    def test_width_auto_falls_back_to_the_default_without_a_terminal(self):
        plain, plain_out = run_cli("--at", "2026-11-09T12:00", "day")
        auto, auto_out = run_cli("--at", "2026-11-09T12:00", "--width", "auto", "day")
        self.assertEqual((auto, auto_out), (plain, plain_out))

    def test_width_auto_uses_the_terminal_width(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        out = Tty()
        with mock.patch(
            "timeleft.cli.shutil.get_terminal_size",
            return_value=os.terminal_size((60, 24)),
        ), redirect_stdout(out):
            code = main(["--at", "2026-11-09T12:00", "--width", "auto", "day"])
        self.assertEqual(code, 0)
        line = re.sub(r"\033\[[0-9;]*m", "", out.getvalue().strip())
        self.assertLessEqual(len(line), 60)
        bar = line.split("[", 1)[1].split("]", 1)[0]
        self.assertEqual(len(bar), 28)

    def test_non_numeric_width_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--width", "wide", "day")
        self.assertEqual(caught.exception.code, 2)


class MainTest(unittest.TestCase):
    def test_default_prints_every_period(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--plain")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 5)
        for period in ("day", "week", "month", "quarter", "year"):
            self.assertTrue(any(line.startswith(period) for line in lines), period)

    def test_explicit_periods(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--plain", "day", "year")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("day"))
        self.assertTrue(lines[1].startswith("year"))

    def test_day_is_half_gone_at_noon(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--plain", "day")
        self.assertEqual(code, 0)
        self.assertIn("50.0%", out)
        self.assertIn("12h 00m left", out)

    def test_json_output(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["now"], "2026-11-09T12:00:00")
        self.assertEqual(len(payload["periods"]), 5)
        day = payload["periods"][0]
        self.assertEqual(day["period"], "day")
        self.assertAlmostEqual(day["fraction"], 0.5)
        self.assertEqual(day["remaining_seconds"], 43200)
        self.assertEqual(day["remaining"], "12h 00m")
        self.assertEqual(day["start"], "2026-11-09T00:00:00")
        self.assertEqual(day["end"], "2026-11-10T00:00:00")
        self.assertEqual(day["total_seconds"], 86400)
        self.assertEqual(day["total"], "1d 00h")

    def test_width_option(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--width", "3", "day")
        self.assertEqual(code, 0)
        self.assertIn("[\u2588\u2591\u2591]", out)

    def test_partial_option_draws_a_smoother_bar_edge(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:30", "--width", "10", "--partial", "day"
        )
        self.assertEqual(code, 0)
        self.assertIn("[\u2588\u2588\u2588\u2588\u2588\u258e" + "\u2591" * 4 + "]", out)

    def test_partial_option_is_rejected_with_ascii(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--partial", "--ascii", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_partial_option_is_ignored_in_plain_mode(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--partial", "--plain", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "day      50.0%  12h 00m left\n")

    def test_ascii_option_replaces_block_glyphs(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--width", "3", "--ascii", "day")
        self.assertEqual(code, 0)
        self.assertIn("[#--]", out)
        self.assertNotIn("\u2588", out)
        self.assertNotIn("\u2591", out)

    def test_ascii_stdout_falls_back_automatically(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="ascii")
        with redirect_stdout(stream):
            code = main(["--at", "2026-11-09T12:00", "--width", "3", "day"])
        stream.flush()
        self.assertEqual(code, 0)
        self.assertIn("[#--]", buffer.getvalue().decode("ascii"))

    def test_week_start_sunday_shifts_week_span(self):
        code, out = run_cli(
            "--at", "2026-11-11T12:00", "--json", "--week-start", "sunday", "week"
        )
        self.assertEqual(code, 0)
        week = json.loads(out)["periods"][0]
        self.assertEqual(week["start"], "2026-11-08T00:00:00")
        self.assertEqual(week["end"], "2026-11-15T00:00:00")

    def test_week_start_defaults_to_monday(self):
        code, out = run_cli("--at", "2026-11-11T12:00", "--json", "week")
        self.assertEqual(code, 0)
        week = json.loads(out)["periods"][0]
        self.assertEqual(week["start"], "2026-11-09T00:00:00")

    def test_week_start_accepts_any_weekday(self):
        code, out = run_cli(
            "--at", "2026-11-11T12:00", "--json", "--week-start", "friday", "week"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["start"], "2026-11-06T00:00:00")

    def test_week_start_accepts_three_letter_names(self):
        code, out = run_cli(
            "--at", "2026-11-11T12:00", "--json", "--week-start", "sat", "week"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["start"], "2026-11-07T00:00:00")

    def test_week_start_accepts_long_abbreviations(self):
        for name, expected in (
            ("tues", "2026-11-10"),
            ("weds", "2026-11-11"),
            ("thurs", "2026-11-05"),
        ):
            with self.subTest(name=name):
                code, out = run_cli(
                    "--at", "2026-11-11T12:00", "--json", "--week-start", name, "week"
                )
                self.assertEqual(code, 0)
                self.assertEqual(
                    json.loads(out)["periods"][0]["start"], expected + "T00:00:00"
                )

    def test_week_start_is_case_insensitive(self):
        for name, expected in (("Sunday", "2026-11-08"), ("SAT", "2026-11-07")):
            with self.subTest(name=name):
                code, out = run_cli(
                    "--at", "2026-11-11T12:00", "--json", "--week-start", name, "week"
                )
                self.assertEqual(code, 0)
                self.assertEqual(
                    json.loads(out)["periods"][0]["start"], expected + "T00:00:00"
                )

    def test_bad_week_start_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--week-start", "funday", "week")
        self.assertEqual(caught.exception.code, 2)

    def test_countdown_prints_only_remaining(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--countdown", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_countdown_prints_one_line_per_period(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--countdown", "day", "week")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["12h 00m", "6d 12h"])

    def test_precision_option_controls_table_decimals(self):
        code, out = run_cli(
            "--at", "2026-11-09T14:30", "--precision", "2", "--plain", "day"
        )
        self.assertEqual(code, 0)
        self.assertIn("60.42%", out)

    def test_precision_option_controls_percent_mode(self):
        code, out = run_cli(
            "--at", "2026-11-09T14:30", "--precision", "0", "--percent", "day"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "60%\n")

    def test_precision_option_controls_json_percent(self):
        code, out = run_cli(
            "--at", "2026-11-09T14:30", "--json", "--precision", "2", "day"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["percent"], 60.42)

    def test_json_reports_percent_left(self):
        code, out = run_cli(
            "--at", "2026-11-09T14:30", "--json", "--precision", "0", "day"
        )
        self.assertEqual(code, 0)
        row = json.loads(out)["periods"][0]
        self.assertEqual(row["percent"], 60.0)
        self.assertEqual(row["percent_left"], 40.0)

    def test_json_percent_left_matches_percent_left_mode(self):
        code, out = run_cli("--at", "2026-11-09T14:30", "--percent-left", "day", "week")
        self.assertEqual(code, 0)
        printed = [line.rstrip("%") for line in out.splitlines()]
        code, payload = run_cli(
            "--at", "2026-11-09T14:30", "--json", "day", "week"
        )
        self.assertEqual(code, 0)
        as_json = [
            "%.1f" % row["percent_left"] for row in json.loads(payload)["periods"]
        ]
        self.assertEqual(printed, as_json)

    def test_bad_precision_fails(self):
        for value in ("-1", "7"):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit) as caught:
                    run_cli("--precision", value, "day")
                self.assertEqual(caught.exception.code, 2)

    def test_percent_prints_only_percentage(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--percent", "day", "year")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "50.0%")
        self.assertTrue(lines[1].endswith("%"))
        self.assertNotIn("left", out)

    def test_percent_left_prints_the_share_still_ahead(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--percent-left", "day", "week")
        self.assertEqual(code, 0)
        self.assertEqual(out, "50.0%\n92.9%\n")

    def test_precision_option_controls_percent_left_mode(self):
        code, out = run_cli(
            "--at", "2026-11-09T14:30", "--precision", "2", "--percent-left", "day"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "39.58%\n")

    def test_percent_left_is_mutually_exclusive_with_percent(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--percent", "--percent-left", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_labels_prefixes_value_only_lines_with_the_period(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--countdown", "--labels", "day", "week"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "day 12h 00m\nweek 6d 12h\n")

    def test_labels_work_with_percent_and_total_modes(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--percent", "--labels", "day"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "day 50.0%\n")
        code, out = run_cli("--at", "2026-11-09T12:00", "--total", "--labels", "year")
        self.assertEqual(code, 0)
        self.assertEqual(out, "year 365d 00h\n")

    def test_labels_do_not_change_the_table(self):
        unflagged = run_cli("--at", "2026-11-09T12:00", "--plain", "day")
        flagged = run_cli("--at", "2026-11-09T12:00", "--plain", "--labels", "day")
        self.assertEqual(flagged, unflagged)

    def test_elapsed_prints_only_time_spent(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--elapsed", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_elapsed_prints_one_line_per_period(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--elapsed", "day", "week")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["12h 00m", "12h 00m"])

    def test_total_prints_period_lengths(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--total", "day", "week", "year"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["1d 00h", "7d 00h", "365d 00h"])

    def test_total_includes_the_opt_in_hour(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--total", "hour")
        self.assertEqual(code, 0)
        self.assertEqual(out, "1h 00m\n")

    def test_total_and_countdown_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--total", "--countdown", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_elapsed_is_in_json_output(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["elapsed"], "12h 00m")

    def test_until_prints_remaining(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--until", "2026-11-10T12:00")
        self.assertEqual(code, 0)
        self.assertEqual(out, "1d 00h\n")

    def test_until_accepts_the_same_forms_as_at(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--until", "in 2 hours")
        self.assertEqual(code, 0)
        self.assertEqual(out, "2h 00m\n")

    def test_until_accepts_end_of_period(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--until", "end of week")
        self.assertEqual(code, 0)
        self.assertEqual(out, "6d 12h\n")

    def test_until_end_of_week_honours_week_start(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--week-start", "sunday", "--until", "eow"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "5d 12h\n")

    def test_until_accepts_end_of_month_alias(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--until", "eom")
        self.assertEqual(code, 0)
        self.assertEqual(out, "21d 12h\n")

    def test_at_accepts_end_of_year(self):
        code, out = run_cli("--at", "eoy", "day", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("0.0%", out)

    def test_until_in_the_past_prints_zero(self):
        code, out = run_cli("--at", "2026-11-10T12:00", "--until", "2026-11-09T12:00")
        self.assertEqual(code, 0)
        self.assertEqual(out, "0s\n")

    def test_until_json_output(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--json", "--until", "2026-11-11T18:30"
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["now"], "2026-11-09T12:00:00")
        self.assertEqual(payload["until"], "2026-11-11T18:30:00")
        self.assertEqual(payload["remaining_seconds"], 196200)
        self.assertEqual(payload["remaining"], "2d 06h")

    def test_since_prints_elapsed(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--since", "2026-11-09T10:30")
        self.assertEqual(code, 0)
        self.assertEqual(out, "1h 30m\n")

    def test_since_accepts_period_boundaries(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--since", "sod")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_since_in_the_future_prints_zero(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--since", "2026-11-10T12:00")
        self.assertEqual(code, 0)
        self.assertEqual(out, "0s\n")

    def test_since_json_output(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--json", "--since", "2026-11-01T00:00"
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["now"], "2026-11-09T12:00:00")
        self.assertEqual(payload["since"], "2026-11-01T00:00:00")
        self.assertEqual(payload["elapsed_seconds"], 734400)
        self.assertEqual(payload["elapsed"], "8d 12h")

    def test_since_and_until_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--since", "sod", "--until", "eod")
        self.assertEqual(caught.exception.code, 2)

    def test_bad_since_fails(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            run_cli("--since", "not-a-date")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("not-a-date", stderr.getvalue())

    def test_bad_until_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--until", "not-a-date")
        self.assertEqual(caught.exception.code, 2)

    def test_empty_at_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--at", "", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_empty_until_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--until", "")
        self.assertEqual(caught.exception.code, 2)

    def test_empty_since_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--since", "")
        self.assertEqual(caught.exception.code, 2)

    def test_until_and_countdown_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--until", "tomorrow", "--countdown")
        self.assertEqual(caught.exception.code, 2)

    def test_elapsed_and_countdown_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--elapsed", "--countdown", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_countdown_and_percent_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--countdown", "--percent", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_hour_period_is_selectable(self):
        code, out = run_cli("--at", "2026-11-09T12:30", "--json", "hour")
        self.assertEqual(code, 0)
        hour = json.loads(out)["periods"][0]
        self.assertEqual(hour["period"], "hour")
        self.assertEqual(hour["remaining_seconds"], 1800)

    def test_hour_accepts_alias_and_plural(self):
        for name in ("h", "hours", "H"):
            with self.subTest(name=name):
                code, out = run_cli("--at", "2026-11-09T12:30", "--json", name)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["periods"][0]["period"], "hour")

    def test_hour_is_not_in_the_default_report(self):
        code, out = run_cli("--at", "2026-11-09T12:30", "--json")
        self.assertEqual(code, 0)
        periods = [row["period"] for row in json.loads(out)["periods"]]
        self.assertEqual(periods, ["day", "week", "month", "quarter", "year"])

    def test_end_of_hour_target(self):
        code, out = run_cli("--at", "2026-11-09T12:30", "--until", "eoh")
        self.assertEqual(code, 0)
        self.assertEqual(out, "30m 00s\n")

    def test_start_of_hour_target(self):
        code, out = run_cli("--at", "soh", "--json", "day")
        self.assertEqual(code, 0)
        now = datetime.fromisoformat(json.loads(out)["now"])
        self.assertEqual((now.minute, now.second), (0, 0))

    def test_single_letter_aliases(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--plain", "d", "y")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertTrue(lines[0].startswith("day"))
        self.assertTrue(lines[1].startswith("year"))

    def test_alias_in_json_output(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "q")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["period"], "quarter")

    def test_alias_with_countdown(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--countdown", "w")
        self.assertEqual(code, 0)
        self.assertEqual(out, "6d 12h\n")

    def test_period_unit_abbreviations(self):
        cases = {
            "hr": "hour", "hrs": "hour",
            "wk": "week", "wks": "week",
            "mo": "month", "mos": "month",
            "qtr": "quarter", "qtrs": "quarter",
            "yr": "year", "yrs": "year",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                code, out = run_cli("--at", "2026-11-09T12:00", "--json", name)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["periods"][0]["period"], expected)

    def test_period_names_accept_plurals(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "days", "Weeks")
        self.assertEqual(code, 0)
        periods = [row["period"] for row in json.loads(out)["periods"]]
        self.assertEqual(periods, ["day", "week"])

    def test_period_names_accept_uppercase_aliases(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "Q")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["period"], "quarter")

    def test_repeated_periods_are_deduplicated(self):
        code, out = run_cli("day", "d", "--plain", "--at", "2026-11-09T12:00")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertTrue(out.startswith("day"))

    def test_repeated_periods_are_deduplicated_in_json(self):
        code, out = run_cli("--json", "--at", "2026-11-09T12:00", "week", "w")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["periods"]), 1)

    def test_deduplicated_periods_keep_their_order(self):
        code, out = run_cli("--json", "--at", "2026-11-09T12:00", "week", "day", "week")
        self.assertEqual(code, 0)
        self.assertEqual(
            [row["period"] for row in json.loads(out)["periods"]], ["week", "day"]
        )

    def test_comma_separated_periods(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "day,week")
        self.assertEqual(code, 0)
        self.assertEqual(
            [row["period"] for row in json.loads(out)["periods"]], ["day", "week"]
        )

    def test_comma_separated_periods_allow_spaces_and_dedupe(self):
        code, out = run_cli(
            "--at", "2026-11-09T12:00", "--json", "day, week, d"
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            [row["period"] for row in json.loads(out)["periods"]], ["day", "week"]
        )

    def test_comma_separated_periods_reject_empty_names(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("day,")
        self.assertEqual(caught.exception.code, 2)

    def test_plural_of_unknown_period_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("fortnights")
        self.assertEqual(caught.exception.code, 2)

    def test_unknown_period_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("fortnight")
        self.assertEqual(caught.exception.code, 2)

    def test_bad_width_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--width", "0", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_relative_at_is_measured_from_now(self):
        code, out = run_cli("--at", "+90m", "--json", "day")
        self.assertEqual(code, 0)
        reported = datetime.fromisoformat(json.loads(out)["now"])
        offset = (reported - datetime.now()).total_seconds()
        self.assertAlmostEqual(offset, 5400, delta=10)

    def test_at_keyword_tomorrow_starts_the_next_day(self):
        code, out = run_cli("--at", "tomorrow", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["remaining_seconds"], 86400)

    def test_at_weekday_with_clock_time(self):
        code, out = run_cli("--at", "friday noon", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["remaining_seconds"], 43200)
        self.assertEqual(
            datetime.fromisoformat(json.loads(out)["now"]).weekday(), 4
        )

    def test_at_named_clock_combines_with_day_keyword(self):
        code, out = run_cli("--at", "tomorrow noon", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["remaining_seconds"], 43200)

    def test_at_twelve_hour_clock(self):
        code, out = run_cli("--at", "6:30pm", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["remaining_seconds"], 19800)

    def test_at_week_targets_honour_week_start(self):
        fixed = datetime(2026, 11, 11, 12, 0)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        cases = {
            "sow": "2026-11-08T00:00:00",
            "start of week": "2026-11-08T00:00:00",
            "eow": "2026-11-15T00:00:00",
            "end of week": "2026-11-15T00:00:00",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                with mock.patch("timeleft.cli.datetime", FixedDatetime):
                    code, out = run_cli(
                        "--at", text, "--week-start", "sunday", "--json", "day"
                    )
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(out)["now"], expected)

    def test_bad_at_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--at", "not-a-date", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_bad_at_error_names_the_value(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            run_cli("--at", "not-a-date", "day")
        self.assertIn("not-a-date", stderr.getvalue())

    def test_bad_at_error_explains_the_reason(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            run_cli("--at", "2026-13", "day")
        self.assertIn("month must be between 1 and 12", stderr.getvalue())

    def test_bad_at_error_names_the_day_anchor(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            run_cli("--at", "tomorrow 25:00", "day")
        self.assertIn("tomorrow", stderr.getvalue())

    def test_bad_until_error_explains_the_reason(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            run_cli("--until", "tomorrow 25:00")
        self.assertIn("expected a clock time", stderr.getvalue())

    def test_bad_until_error_names_the_value(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            run_cli("--until", "not-a-date")
        self.assertIn("not-a-date", stderr.getvalue())

    def test_version_exits_zero(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--version")
        self.assertEqual(caught.exception.code, 0)


class WatchTest(unittest.TestCase):
    def test_watch_redraws_until_interrupted(self):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch(
            "timeleft.cli.time.sleep", side_effect=KeyboardInterrupt
        ):
            code = main(["--at", "2026-11-09T12:00", "--plain", "--watch", "5", "day"])
        self.assertEqual(code, 0)
        self.assertIn("12h 00m left", out.getvalue())

    def test_watch_sleeps_between_frames(self):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch(
            "timeleft.cli.time.sleep", side_effect=[None, None, KeyboardInterrupt]
        ) as sleep:
            code = main(["--at", "2026-11-09T12:00", "--plain", "--watch", "2.5", "day"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().count("left"), 3)
        self.assertEqual(sleep.call_args_list, [mock.call(2.5)] * 3)

    def test_watch_interval_must_be_positive(self):
        for seconds in ("0", "-1"):
            with self.subTest(seconds=seconds):
                with self.assertRaises(SystemExit) as caught:
                    run_cli("--watch", seconds, "day")
                self.assertEqual(caught.exception.code, 2)

    def test_watch_rejects_non_finite_intervals(self):
        for value in ("nan", "inf", "1e309", "1e308", "0", "-5"):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit):
                    run_cli("--watch", value, "day")

    def test_watch_rejects_json(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--watch", "1", "--json", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_watch_redraws_the_until_countdown(self):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch(
            "timeleft.cli.time.sleep", side_effect=KeyboardInterrupt
        ):
            code = main(
                ["--at", "2026-11-09T12:00", "--until", "2026-11-09T13:00", "--watch", "1"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "1h 00m\n")


class ShortOptionsTest(unittest.TestCase):
    def test_json_short_flag(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-j", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["period"], "day")

    def test_plain_short_flag(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-p", "day")
        self.assertEqual(code, 0)
        self.assertNotIn("[", out)

    def test_ascii_and_width_short_flags(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-a", "-w", "3", "day")
        self.assertEqual(code, 0)
        self.assertIn("[#--]", out)

    def test_countdown_short_flag(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-c", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_elapsed_short_flag(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-e", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_version_short_flag(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("-V")
        self.assertEqual(caught.exception.code, 0)


class BrokenPipeTest(unittest.TestCase):
    def test_main_returns_zero_when_stdout_closes(self):
        with mock.patch("timeleft.cli.emit_report", side_effect=BrokenPipeError):
            code, out = run_cli("--at", "2026-11-09T12:00", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_watch_returns_zero_when_stdout_closes(self):
        with mock.patch("timeleft.cli.emit_report", side_effect=BrokenPipeError):
            with mock.patch("timeleft.cli.time.sleep"):
                code, out = run_cli("--watch", "1", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_silence_broken_pipe_tolerates_streams_without_fileno(self):
        from timeleft.cli import silence_broken_pipe

        silence_broken_pipe()


if __name__ == "__main__":
    unittest.main()


class BeginningOfTest(unittest.TestCase):
    def test_beginning_of_matches_start_of(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_target("beginning of week", base), datetime(2026, 11, 9))
        self.assertEqual(
            parse_target("the beginning of the week", base), datetime(2026, 11, 9)
        )
        self.assertEqual(
            parse_target("beginning of next month", base), datetime(2026, 12, 1)
        )
        self.assertEqual(parse_target("beginning of tomorrow", base), datetime(2026, 11, 10))


class BareMonthNameTest(unittest.TestCase):
    def test_bare_month_is_the_first_of_that_month(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("december", base), datetime(2026, 12, 1))
        self.assertEqual(parse_moment("dec", base), datetime(2026, 12, 1))
        self.assertEqual(parse_moment("nov", base), datetime(2027, 11, 1))

    def test_bare_month_rolls_to_next_year_when_past(self):
        base = datetime(2026, 12, 20, 12, 0)
        self.assertEqual(parse_moment("january", base), datetime(2027, 1, 1))


class StartEndModesTest(unittest.TestCase):
    def test_start_prints_period_start(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--start", "day", "month")
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-11-09T00:00:00\n2026-11-01T00:00:00\n")

    def test_end_prints_period_end(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--end", "day", "month")
        self.assertEqual(code, 0)
        self.assertEqual(out, "2026-11-10T00:00:00\n2026-12-01T00:00:00\n")

    def test_start_and_end_respect_labels(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--start", "--labels", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "day 2026-11-09T00:00:00\n")

    def test_start_and_end_are_exclusive_with_other_value_modes(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["--start", "--countdown", "day"])


class FractionModeTest(unittest.TestCase):
    def test_fraction_prints_elapsed_share(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--fraction", "day", "year")
        self.assertEqual(code, 0)
        self.assertEqual(out, "0.500000\n0.856164\n")

    def test_fraction_honours_labels(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--fraction", "--labels", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "day 0.500000\n")


class DateThenClockTest(unittest.TestCase):
    def test_iso_date_can_be_followed_by_a_clock_without_at(self):
        self.assertEqual(parse_moment("2026-11-09 5pm"), datetime(2026, 11, 9, 17, 0))
        self.assertEqual(parse_moment("2026-11-09 09:30"), datetime(2026, 11, 9, 9, 30))
        self.assertEqual(parse_moment("2026-11-09 12:00:30"), datetime(2026, 11, 9, 12, 0, 30))

    def test_unparseable_text_after_a_date_still_fails(self):
        with self.assertRaises(ValueError):
            parse_moment("2026-11-09 not-a-clock")


class EpochMomentTest(unittest.TestCase):
    def test_at_epoch_seconds(self):
        self.assertEqual(
            parse_moment("@1700000000"),
            datetime.fromtimestamp(1700000000).replace(microsecond=0),
        )

    def test_at_epoch_milliseconds(self):
        expected = datetime.fromtimestamp(1700000000).replace(microsecond=0)
        self.assertEqual(parse_moment("@1700000000000"), expected)


class MoreShortOptionsTest(unittest.TestCase):
    def test_labels_short_option(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-l", "-c", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "day 12h 00m\n")

    def test_total_short_option(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "-t", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "1d 00h\n")


class WeekendMomentTest(unittest.TestCase):
    def test_weekend_is_the_coming_saturday(self):
        monday = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("weekend", monday), datetime(2026, 11, 14))
        self.assertEqual(parse_moment("this weekend", monday), datetime(2026, 11, 14))

    def test_weekend_today_stays_today(self):
        saturday = datetime(2026, 11, 14, 12, 0)
        self.assertEqual(parse_moment("weekend", saturday), datetime(2026, 11, 14))

    def test_next_weekend_is_a_week_later(self):
        monday = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("next weekend", monday), datetime(2026, 11, 21))


class BarStyleOptionTest(unittest.TestCase):
    def test_bar_style_selects_characters(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--width", "10", "--bar-style", "line", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "day     [━━━━━─────]  50.0%  12h 00m left\n")

    def test_bar_style_conflicts_with_ascii(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["--bar-style", "dot", "--ascii", "day"])
