import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from timeleft.cli import format_row, main, parse_moment, supports_block_glyphs


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

    def test_z_suffix_becomes_local_naive(self):
        moment = parse_moment("2026-11-09T12:00:00Z")
        self.assertIsNone(moment.tzinfo)
        expected = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).astimezone()
        self.assertEqual(moment, expected.replace(tzinfo=None))

    def test_lowercase_z_suffix_is_utc_too(self):
        self.assertEqual(
            parse_moment("2026-11-09T12:00:00z"),
            parse_moment("2026-11-09T12:00:00Z"),
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
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_relative_offset_needs_whole_number(self):
        with self.assertRaises(ValueError):
            parse_moment("+1.5h", now=datetime(2026, 11, 9, 12, 0))

    def test_relative_offset_with_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_moment("+90x", now=datetime(2026, 11, 9, 12, 0))

    def test_clock_time_uses_today(self):
        base = datetime(2026, 11, 9, 12, 0)
        self.assertEqual(parse_moment("15:30", now=base), datetime(2026, 11, 9, 15, 30))
        self.assertEqual(parse_moment("9:30", now=base), datetime(2026, 11, 9, 9, 30))
        self.assertEqual(
            parse_moment("15:30:45", now=base), datetime(2026, 11, 9, 15, 30, 45)
        )

    def test_clock_time_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            parse_moment("25:00", now=datetime(2026, 11, 9, 12, 0))

    def test_twelve_hour_clock_times(self):
        base = datetime(2026, 11, 9, 12, 0)
        cases = {
            "9am": datetime(2026, 11, 9, 9, 0),
            "9:30pm": datetime(2026, 11, 9, 21, 30),
            "12am": datetime(2026, 11, 9, 0, 0),
            "12:15PM": datetime(2026, 11, 9, 12, 15),
            "6:30 pm": datetime(2026, 11, 9, 18, 30),
            "11:59:30 a.m.": datetime(2026, 11, 9, 11, 59, 30),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_moment(text, now=base), expected)

    def test_twelve_hour_clock_time_with_day_anchor(self):
        base = datetime(2026, 11, 11, 12, 0)
        self.assertEqual(parse_moment("tomorrow 9am", now=base), datetime(2026, 11, 12, 9, 0))
        self.assertEqual(parse_moment("9pm friday", now=base), datetime(2026, 11, 13, 21, 0))

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

    def test_named_clock_times(self):
        base = datetime(2026, 11, 9, 18, 25, 40, 123456)
        self.assertEqual(parse_moment("noon", now=base), datetime(2026, 11, 9, 12, 0))
        self.assertEqual(parse_moment("Midnight", now=base), datetime(2026, 11, 9))
        self.assertEqual(
            parse_moment("Tomorrow noon", now=base), datetime(2026, 11, 10, 12, 0)
        )
        self.assertEqual(
            parse_moment("midnight tomorrow", now=base), datetime(2026, 11, 10)
        )

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

    def test_percent_prints_only_percentage(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--percent", "day", "year")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "50.0%")
        self.assertTrue(lines[1].endswith("%"))
        self.assertNotIn("left", out)

    def test_elapsed_prints_only_time_spent(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--elapsed", "day")
        self.assertEqual(code, 0)
        self.assertEqual(out, "12h 00m\n")

    def test_elapsed_prints_one_line_per_period(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--elapsed", "day", "week")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["12h 00m", "12h 00m"])

    def test_elapsed_is_in_json_output(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "day")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["elapsed"], "12h 00m")

    def test_elapsed_and_countdown_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--elapsed", "--countdown", "day")
        self.assertEqual(caught.exception.code, 2)

    def test_countdown_and_percent_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--countdown", "--percent", "day")
        self.assertEqual(caught.exception.code, 2)

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

    def test_period_names_accept_plurals(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "days", "Weeks")
        self.assertEqual(code, 0)
        periods = [row["period"] for row in json.loads(out)["periods"]]
        self.assertEqual(periods, ["day", "week"])

    def test_period_names_accept_uppercase_aliases(self):
        code, out = run_cli("--at", "2026-11-09T12:00", "--json", "Q")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["periods"][0]["period"], "quarter")

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
