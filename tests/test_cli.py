"""Tests for the timeleft command line interface."""

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from timeleft.cli import format_row, main, parse_moment


def run_cli(*argv):
    """Run the CLI and return (exit code, stdout)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class ParseMomentTest(unittest.TestCase):
    def test_plain_iso(self):
        self.assertEqual(parse_moment("2026-11-09T12:00"), datetime(2026, 11, 9, 12, 0))

    def test_date_only(self):
        self.assertEqual(parse_moment("2026-11-09"), datetime(2026, 11, 9))

    def test_z_suffix_becomes_local_naive(self):
        moment = parse_moment("2026-11-09T12:00:00Z")
        self.assertIsNone(moment.tzinfo)
        expected = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).astimezone()
        self.assertEqual(moment, expected.replace(tzinfo=None))

    def test_offset_is_converted(self):
        moment = parse_moment("2026-11-09T12:00:00+02:00")
        self.assertIsNone(moment.tzinfo)
        expected = datetime(2026, 11, 9, 12, 0, tzinfo=timezone(timedelta(hours=2))).astimezone()
        self.assertEqual(moment, expected.replace(tzinfo=None))

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_moment("yesterday-ish")


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

    def test_width_option(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--width", "3", "day")
        self.assertEqual(code, 0)
        self.assertIn("[\u2588\u2591\u2591]", out)

    def test_unknown_period_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("fortnight")
        self.assertEqual(caught.exception.code, 2)

    def test_bad_width_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--width", "0", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_bad_at_fails(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--at", "not-a-date", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_version_exits_zero(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--version")
        self.assertEqual(caught.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
