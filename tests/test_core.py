import unittest
from datetime import datetime

from timeleft.core import PERIODS, build_report, format_duration, render_bar, span_for


class SpanTest(unittest.TestCase):
    def setUp(self):
        # 2026-11-09 is a Monday.
        self.now = datetime(2026, 11, 9, 14, 30)

    def test_day_span(self):
        span = span_for("day", self.now)
        self.assertEqual(span.start, datetime(2026, 11, 9))
        self.assertEqual(span.end, datetime(2026, 11, 10))

    def test_week_starts_on_monday(self):
        span = span_for("week", self.now)
        self.assertEqual(span.start, datetime(2026, 11, 9))
        self.assertEqual(span.end, datetime(2026, 11, 16))

    def test_week_span_contains_sunday(self):
        span = span_for("week", datetime(2026, 11, 15, 23, 59))
        self.assertEqual(span.start, datetime(2026, 11, 9))
        self.assertEqual(span.end, datetime(2026, 11, 16))

    def test_week_can_start_on_sunday(self):
        span = span_for("week", datetime(2026, 11, 11, 9, 0), week_start=6)
        self.assertEqual(span.start, datetime(2026, 11, 8))
        self.assertEqual(span.end, datetime(2026, 11, 15))

    def test_sunday_week_contains_saturday_night(self):
        span = span_for("week", datetime(2026, 11, 14, 23, 59), week_start=6)
        self.assertTrue(span.contains(datetime(2026, 11, 14, 23, 59)))
        self.assertEqual(span.end, datetime(2026, 11, 15))

    def test_week_start_out_of_range_is_rejected(self):
        for bad in (-1, 7):
            with self.subTest(week_start=bad):
                with self.assertRaises(ValueError):
                    span_for("week", self.now, week_start=bad)

    def test_month_span(self):
        span = span_for("month", self.now)
        self.assertEqual(span.start, datetime(2026, 11, 1))
        self.assertEqual(span.end, datetime(2026, 12, 1))

    def test_month_span_december_rolls_over_year(self):
        span = span_for("month", datetime(2026, 12, 31, 23, 0))
        self.assertEqual(span.start, datetime(2026, 12, 1))
        self.assertEqual(span.end, datetime(2027, 1, 1))

    def test_quarter_span(self):
        span = span_for("quarter", self.now)
        self.assertEqual(span.start, datetime(2026, 10, 1))
        self.assertEqual(span.end, datetime(2027, 1, 1))

    def test_all_quarters(self):
        expected = {
            1: datetime(2026, 1, 1),
            4: datetime(2026, 4, 1),
            7: datetime(2026, 7, 1),
            10: datetime(2026, 10, 1),
        }
        for month, start in expected.items():
            with self.subTest(month=month):
                self.assertEqual(span_for("quarter", datetime(2026, month, 15)).start, start)

    def test_year_span(self):
        span = span_for("year", self.now)
        self.assertEqual(span.start, datetime(2026, 1, 1))
        self.assertEqual(span.end, datetime(2027, 1, 1))

    def test_unknown_period_is_rejected(self):
        with self.assertRaises(ValueError):
            span_for("fortnight", self.now)

    def test_all_named_periods_resolve(self):
        for period in PERIODS:
            with self.subTest(period=period):
                span = span_for(period, self.now)
                self.assertTrue(span.contains(self.now))
                self.assertGreater(span.total_seconds, 0)

    def test_fraction_is_clamped_to_period(self):
        span = span_for("day", self.now)
        self.assertEqual(span.fraction_elapsed(datetime(2026, 11, 8, 23, 0)), 0.0)
        self.assertEqual(span.fraction_elapsed(datetime(2026, 11, 10, 1, 0)), 1.0)

    def test_half_of_day(self):
        span = span_for("day", self.now)
        self.assertAlmostEqual(span.fraction_elapsed(datetime(2026, 11, 9, 12, 0)), 0.5)

    def test_remaining_seconds(self):
        span = span_for("day", datetime(2026, 11, 9, 23, 0))
        self.assertEqual(span.remaining_seconds(datetime(2026, 11, 9, 23, 0)), 3600)


class FormatDurationTest(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_duration(0), "0s")

    def test_seconds_only(self):
        self.assertEqual(format_duration(45), "45s")

    def test_minutes(self):
        self.assertEqual(format_duration(185), "3m 05s")

    def test_hours(self):
        self.assertEqual(format_duration(2 * 3600 + 7 * 60), "2h 07m")

    def test_days(self):
        self.assertEqual(format_duration(5 * 86400 + 3600), "5d 01h")

    def test_negative_clamps_to_zero(self):
        self.assertEqual(format_duration(-90), "0s")

    def test_rounds_to_nearest_second(self):
        self.assertEqual(format_duration(59.6), "1m 00s")


class RenderBarTest(unittest.TestCase):
    def test_empty_bar(self):
        self.assertEqual(render_bar(0.0, 4), "\u2591" * 4)

    def test_full_bar(self):
        self.assertEqual(render_bar(1.0, 4), "\u2588" * 4)

    def test_half_bar(self):
        self.assertEqual(render_bar(0.5, 4), "\u2588\u2588\u2591\u2591")

    def test_width_is_respected(self):
        for fraction in (0.0, 0.13, 0.5, 0.99, 1.0):
            with self.subTest(fraction=fraction):
                self.assertEqual(len(render_bar(fraction, 10)), 10)

    def test_fraction_outside_range_is_clamped(self):
        self.assertEqual(render_bar(-3.0, 4), "\u2591" * 4)
        self.assertEqual(render_bar(42.0, 4), "\u2588" * 4)

    def test_bad_width(self):
        with self.assertRaises(ValueError):
            render_bar(0.5, 0)

    def test_ascii_style(self):
        self.assertEqual(render_bar(0.5, 4, "ascii"), "##--")
        self.assertEqual(render_bar(0.0, 3, "ascii"), "---")
        self.assertEqual(render_bar(1.0, 3, "ascii"), "###")

    def test_unknown_style(self):
        with self.assertRaises(ValueError):
            render_bar(0.5, 4, "braille")


class BuildReportTest(unittest.TestCase):
    def test_elapsed_is_formatted(self):
        row = build_report(["day"], datetime(2026, 11, 9, 14, 30))[0]
        self.assertEqual(row["elapsed_seconds"], 52200)
        self.assertEqual(row["elapsed"], "14h 30m")

    def test_period_total_is_included(self):
        day = build_report(["day"], datetime(2026, 11, 9, 14, 30))[0]
        self.assertEqual(day["total_seconds"], 86400)
        self.assertEqual(day["total"], "1d 00h")
        year = build_report(["year"], datetime(2026, 11, 9, 14, 30))[0]
        self.assertEqual(year["total_seconds"], 31536000)
        self.assertEqual(year["total"], "365d 00h")


if __name__ == "__main__":
    unittest.main()
