# Using `timeleft`

`timeleft` shows how much of the current period has already passed, how much is
left, and a bar to see it at a glance. This page is the full command reference;
see [the README](../README.md) for what the tool is and how to install it.

## Synopsis

```console
timeleft [OPTIONS] [PERIOD ...]
```

With no options it prints one line per default period - `day`, `week`, `month`,
`quarter`, `year` - with a progress bar, the percentage elapsed, and the time
remaining.

```console
$ timeleft --at 2026-11-09T12:00
day     [████████████░░░░░░░░░░░░░]  50.0%  12h 00m left
week    [█░░░░░░░░░░░░░░░░░░░░░░░░]   7.1%  6d 12h left
month   [███████░░░░░░░░░░░░░░░░░░]  28.3%  21d 12h left
quarter [██████████░░░░░░░░░░░░░░░]  42.9%  52d 12h left
year    [█████████████████████░░░░]  85.6%  52d 12h left
```

The examples below pin `--at 2026-11-09T12:00` so their output is stable. Drop
the flag to evaluate the real current moment.

## Periods

| Period    | Short        | Plural     | In the default report |
| --------- | ------------ | ---------- | --------------------- |
| `hour`    | `h`, `hr`    | `hours`    | no - opt in           |
| `day`     | `d`          | `days`     | yes                   |
| `week`    | `w`, `wk`    | `weeks`    | yes                   |
| `month`   | `m`, `mo`    | `months`   | yes                   |
| `quarter` | `q`, `qtr`   | `quarters` | yes                   |
| `year`    | `y`, `yr`    | `years`    | yes                   |

- Case does not matter: `Week`, `WEEK` and `w` are the same period.
- The longer abbreviations also take a plural `s`: `hrs`, `wks`, `mos`, `qtrs`,
  `yrs`.
- Repeats are printed once, in the order you first named them. Periods can be
  separated by commas instead of spaces: `timeleft day,week`.

## Choosing periods

```console
$ timeleft week month               # only these two
$ timeleft d w y                    # short forms
$ timeleft days hours               # plurals work too
$ timeleft hour                     # the current clock hour, opt-in
$ timeleft day,week                 # commas work as separators too
```

## Output modes

| Mode           | Flag              | Output                                     |
| -------------- | ----------------- | ------------------------------------------ |
| Table          | *(default)*       | bar, elapsed %, remaining time             |
| Plain table    | `-p`, `--plain`   | elapsed % and remaining time, no bar       |
| ASCII bar      | `-a`, `--ascii`   | bar drawn with `#` and `-`                 |
| Countdown      | `-c`, `--countdown` | remaining time only, one line per period |
| Percentage     | `--percent`       | elapsed percentage only                    |
| Left percent   | `--percent-left`  | percentage still ahead only                |
| Elapsed        | `-e`, `--elapsed` | time already spent only                    |
| Until          | `--until WHEN`    | one line: time left until `WHEN`           |
| Since          | `--since WHEN`    | one line: time elapsed since `WHEN`        |
| Total          | `--total`         | total length of each period, one per line  |
| JSON           | `-j`, `--json`    | structured output                          |

`--countdown`, `--percent`, `--percent-left`, `--elapsed`, `--total`,
`--until` and `--since` are mutually exclusive.
`--json` takes over the formatting whenever it is present.

```console
$ timeleft --at 2026-11-09T12:00 --plain day
day      50.0%  12h 00m left

$ timeleft --at 2026-11-09T12:00 --ascii day
day     [############-------------]  50.0%  12h 00m left

$ timeleft --at 2026-11-09T12:00 --countdown day week
12h 00m
6d 12h

$ timeleft --at 2026-11-09T12:00 --percent day week
50.0%
7.1%

$ timeleft --at 2026-11-09T12:00 --percent-left day week
50.0%
92.9%

$ timeleft --at 2026-11-09T14:30 --precision 2 --percent-left day
39.58%

$ timeleft --at 2026-11-09T12:00 --elapsed day week
12h 00m
12h 00m

$ timeleft --at 2026-11-09T12:00 --total day year
1d 00h
365d 00h
```

The value-only modes are meant to be pasted into status bars, scripts or shell
prompts, e.g. `$(timeleft --countdown day)`. Add `--labels` to keep the period
name on each line, which helps when a widget shows more than one period:

```console
$ timeleft --at 2026-11-09T12:00 --countdown --labels day week
day 12h 00m
week 6d 12h
```

Percentages show one decimal place by default. `--precision N` sets the number
of decimals (0 to 6) for the table, `--percent` and the `percent` field in JSON.
`--percent-left` reports the complement of the same percentage.

```console
$ timeleft --at 2026-11-09T14:30 --precision 2 --plain day
day      60.42%  9h 30m left

$ timeleft --at 2026-11-09T14:30 --precision 0 --percent day
60%
```

## Progress bar

`-w`, `--width N` sets the bar width in characters (default `25`, minimum `1`).
`--width auto` sizes the bar to the terminal so the whole row fits on one line;
when the output is not a terminal it falls back to the default width.

```console
$ timeleft --at 2026-11-09T12:00 --width 10 day
day     [█████░░░░░]  50.0%  12h 00m left
```

Bars use `█`/`░` by default. `--ascii` switches to `#`/`-`, and the bar falls
back to ASCII automatically when the output encoding cannot represent the block
characters.

`--partial` fills the leading empty cell with an eighth block, so the bar moves
in smaller steps instead of jumping a whole character. It needs the Unicode bar
and cannot be combined with `--ascii`.

```console
$ timeleft --at 2026-11-09T14:45 --width 10 --partial day
day     [██████▏░░░]  61.5%  9h 15m left
```

## Colors

`--color {auto,always,never}` colors the bar and the percentage by how much of
the period has gone: green below 50%, yellow from 50% to 80%, red above that.
`auto` (the default) colors only when writing to a terminal, and stays plain
when `NO_COLOR` is set or `TERM` is `dumb`. `always` and `never` force the
choice. Colors need a terminal that understands ANSI escapes; `--watch` keeps
them on every redraw.

```console
$ timeleft --color always --at 2026-11-09T12:00 day
```

## Weeks

Weeks start on Monday by default. `--week-start DAY` accepts any weekday name,
its first three letters or a longer abbreviation such as `tues` or `thurs`, and
applies to the current week and to week targets used by `--at` and `--until`.

```console
$ timeleft --at 2026-11-09T12:00 week
week    [█░░░░░░░░░░░░░░░░░░░░░░░░]   7.1%  6d 12h left

$ timeleft --at 2026-11-09T12:00 --week-start sunday week
week    [█████░░░░░░░░░░░░░░░░░░░░]  21.4%  5d 12h left
```

## Picking the moment: `--at WHEN`

By default every report is evaluated at "now". `--at` evaluates at a different
moment; the formats below are all understood.

### ISO 8601 timestamps

```console
$ timeleft --at 2026-11-09T12:00 day
$ timeleft --at 2026-11-09T12:00:00 day
$ timeleft --at 2026-11-09T11:00Z day      # UTC, converted to local time
$ timeleft --at 2026-11-09T12:00+02:00 day # explicit offset, converted to local
$ timeleft --at 2026-11 day               # first moment of that month
$ timeleft --at 2026 day                  # first moment of that year
$ timeleft --at 2026-1-9 day              # leading zeros are optional
$ timeleft --at 2026-W46-1 day            # ISO week date (week 46, Monday)
$ timeleft --at 20261109T1200 day         # compact form, same moment
$ timeleft --at "2026-11-09 12:00" day    # a space between date and time
$ timeleft --at 2026-11-09T12:00+0200 day # the offset colon is optional too
```

### A clock time today

```console
$ timeleft --at 15:30 day
$ timeleft --at 6:30pm day
$ timeleft --at 9:30p day                # the m in am/pm is optional
$ timeleft --at 18.30 day                # a dot also separates hours and minutes
$ timeleft --at 6.30pm day
$ timeleft --at noon day
$ timeleft --at midnight day
$ timeleft --at "5 o'clock" day
$ timeleft --at "5 o'clock pm" day
$ timeleft --at 9 day                  # a bare hour from 0 to 23
$ timeleft --at "tomorrow at 9" day
```

Half and quarter phrases work too, with or without a day anchor:

```console
$ timeleft --at "half past 3" day
$ timeleft --at "quarter past 4pm" day
$ timeleft --at "quarter to 5" day
$ timeleft --at "10 to 5" day
$ timeleft --at "20 past 4" day
$ timeleft --at "tomorrow half past 3" day
```

Numbers may be spelled out, and `o'clock` works like a bare hour:

```console
$ timeleft --at "ten to five" day
$ timeleft --at "twenty past four" day
$ timeleft --at "twenty five to five" day
$ timeleft --at "a quarter to nine" day
$ timeleft --at "five o'clock" day
$ timeleft --at "tomorrow half past seven" day
```

### Offsets from now

A sign followed by one or more number+unit pairs. Units are `s`, `m`, `h`,
`d` and `w`; decimals are allowed.

```console
$ timeleft --at +90m day
$ timeleft --at -45m day
$ timeleft --at +2h30m day
$ timeleft --at "+2h 30m" day
$ timeleft --at +1.5h day
```

Calendar units `mo`/`mon`/`month`/`months`, `q`/`qtr`/`quarter`/`quarters`
(three months) and `y`/`yr`/`year`/`years` move whole months, so month lengths
and leap years are respected. They may be combined with the shorter units and
with each other:

```console
$ timeleft --at +2mo day
$ timeleft --at -1y day
$ timeleft --at "+1y 2mo" day
$ timeleft --at "+1mo 90m" day
$ timeleft --at "+2 quarters" day
```

A fractional calendar amount such as `+1.5mo` is rejected.

### Natural language offsets

```console
$ timeleft --at "in 2 hours" day
$ timeleft --at "2 weeks ago" day
$ timeleft --at "45 minutes from now" day
$ timeleft --at "in half an hour" day
$ timeleft --at "a quarter of an hour" day
$ timeleft --at "three quarters of an hour" day
$ timeleft --at "in an hour and a half" day
$ timeleft --at "in 1 hour 30 minutes" day
$ timeleft --at "in a fortnight" day
$ timeleft --at "in a week and a half" day
$ timeleft --at "a week and a half ago" day
$ timeleft --at "in 2 days and a half" day
$ timeleft --at "2 and a half weeks ago" day
$ timeleft --at "in a couple of hours" day
$ timeleft --at "a few days ago" day
```

Numbers can be spelled out as well as written in digits:

```console
$ timeleft --at "in two hours" day
$ timeleft --at "three days ago" day
$ timeleft --at "in twenty five minutes" day
$ timeleft --at "in one month" day
$ timeleft --at "in a quarter" day
$ timeleft --at "two quarters from now" day
$ timeleft --at "a quarter ago" day
```

Parts add up, and `a`/`an`/`one` mean one. A phrase must be a valid offset:
contradictions such as `in 2 hours ago` and unknown units such as
`in 2 fortnights` are rejected.

Months and years are calendar-aware, so month lengths and leap years do not
drift:

```console
$ timeleft --at "in 2 months" day
$ timeleft --at "in a month" day
$ timeleft --at "1 year 2 months ago" day
$ timeleft --at "in 1 month" day      # 31 Jan becomes 29 Feb in a leap year
```

### Day keywords

```console
$ timeleft --at now day
$ timeleft --at today day
$ timeleft --at tomorrow day
$ timeleft --at yesterday day
$ timeleft --at "day after tomorrow" day
$ timeleft --at "day before yesterday" day
```

### Parts of the day

`morning`, `afternoon`, `evening`, `night` and `tonight` stand for fixed clock
times: 09:00, 15:00, 19:00, 22:00 and 21:00. They work on their own or after a
day keyword, `this` or a weekday, and a plain clock time after one overrides
the fixed hour:

```console
$ timeleft --at morning day
$ timeleft --at "tomorrow morning" day
$ timeleft --at "yesterday evening" day
$ timeleft --at "friday night" day
$ timeleft --at "tomorrow morning at 7" day
```

### Month and day names

A month name with a day number names that date. Without a year it means the
next such date, so a countdown to Christmas keeps working in January; write
the year out to pin it. A clock time can follow as usual.

```console
$ timeleft --until "dec 25"
$ timeleft --until "25 december at noon"
$ timeleft --at "december 25 2027" day
```

### Day of the month

An ordinal day number names that day in the current month. If it has already
passed, or the month is too short for it, the next month where the day exists
is used. `of next month`, `of last month` and `of this month` pick a different
month, and a day that does not fit there is an error.

```console
$ timeleft --until "the 25th"
$ timeleft --at "1st" day
$ timeleft --until "25th of next month"
$ timeleft --at "1st of last month" day
```

### Weekdays

A weekday name means the next occurrence of that day, counting today. Short
forms such as `tues`, `weds` and `thurs` work too. Add `this`, `next` or `last`
to move the day, and a clock time to pick a moment on that day (`at` is
optional):

```console
$ timeleft --at friday day
$ timeleft --at "next friday 9am" day
$ timeleft --at "last tuesday 15:00" day
$ timeleft --at "tomorrow 09:00" day
$ timeleft --at "tomorrow at 9am" day
```

### Period ends and starts

`--at` and `--until` also accept period boundaries, and any of them can carry
a clock time after `at`:


| Phrase                                   | Shorthand            |
| ---------------------------------------- | -------------------- |
| end of hour / day / week / month / quarter / year | `eoh`, `eod`, `eow`, `eom`, `eoq`, `eoy` |
| start of hour / day / week / month / quarter / year | `soh`, `sod`, `sow`, `som`, `soq`, `soy` |
| middle of hour / day / week / month / quarter / year | |
| last day of day / week / month / quarter / year | |
| first day of day / week / month / quarter / year | |
| last day of next / last / this day / week / month / quarter / year | |
| first day of next / last / this day / week / month / quarter / year | |

```console
$ timeleft --at eow day        # evaluate at the end of the current week
$ timeleft --at "start of month" day
$ timeleft --until "last day of the month"
$ timeleft --at "first day of the week" day
```

Boundaries also accept a day-relative anchor, so a time string can be given
without a fixed date:

```console
$ timeleft --until "end of today"
$ timeleft --at "start of tomorrow" day
$ timeleft --until "middle of today"
```

`middle of` (also `middle of the` / `middle of this`) is the exact halfway
point, so `middle of day` is noon and `middle of week` lands on Thursday noon
for a Monday week start. `next` and `last` shift the period first, so
`middle of next week` is the halfway point of the following week:

```console
$ timeleft --until "middle of next week"
$ timeleft --at "middle of last month" day
```

### Next, last and this periods

`next`, `last` and `this` combine with any period name to pick a boundary one
period away from the current one; `start of` and `end of` narrow it further.

```console
$ timeleft --at "last week" day
$ timeleft --until "start of next month"
$ timeleft --at "end of next quarter" day
$ timeleft --at "this year" day

`first day of` and `last day of` take the same shift, so they pick the start or
the end of the neighbouring period:

```console
$ timeleft --until "first day of next month"
$ timeleft --until "last day of next month"
$ timeleft --at "first day of last week" day
```

### Combining an offset with a clock time

Any moment phrase can be followed by `at` and a clock time, which replaces the
time of day:

```console
$ timeleft --at "in 2 days at 09:00" day
$ timeleft --at "2 days ago at 7pm" day
$ timeleft --at "in 1 month at noon" day
```

## Countdown to a moment: `--until WHEN`

`--until` prints only how long is left until `WHEN`. It accepts every format
`--at` accepts, plus the period-boundary phrases above, and measures from the
moment `--at` selects (or from now).

```console
$ timeleft --at 2026-11-09T12:00 --until eod
12h 00m

$ timeleft --at 2026-11-09T12:00 --until eow
6d 12h

$ timeleft --at 2026-11-09T12:00 --until 2026-12-25T00:00
45d 12h
```

A target in the past reports `0s`. With `--json` the result is an object:

```json
{
  "now": "2026-11-09T12:00:00",
  "until": "2026-12-01T00:00:00",
  "remaining_seconds": 1857600,
  "remaining": "21d 12h"
}
```

## Time since a moment: `--since WHEN`

`--since` is the mirror image of `--until`: it prints only how long has passed
since `WHEN`. It accepts the same formats, including the period boundaries, and
measures from the moment `--at` selects (or from now). A moment in the future
reports `0s`.

```console
$ timeleft --at 2026-11-09T12:00 --since sod
12h 00m

$ timeleft --at 2026-11-09T12:00 --since "start of month"
8d 12h

$ timeleft --at 2026-11-09T12:00 --json --since 2026-11-01T00:00
{
  "now": "2026-11-09T12:00:00",
  "since": "2026-11-01T00:00:00",
  "elapsed_seconds": 734400,
  "elapsed": "8d 12h"
}
```

## Live redraw: `--watch SECONDS`

Redraws the report every `SECONDS` until interrupted with `Ctrl-C`. When stdout
is a terminal the screen is cleared between frames, so it behaves like a clock;
combined with `--countdown`, `--percent`, `--elapsed` or `--until` it becomes a
minimal live display.

```console
$ timeleft day --countdown --watch 1
$ timeleft --until eow --watch 60
```

`--watch` needs a positive number of seconds, at most 86400, and cannot be
combined with `--json`. Combining it with `--at` keeps that anchor fixed, so the
output will not change between frames.

## JSON output

Without `--until`, the report is:

```json
{
  "now": "2026-11-09T12:00:00",
  "periods": [
    {
      "period": "day",
      "start": "2026-11-09T00:00:00",
      "end": "2026-11-10T00:00:00",
      "total_seconds": 86400,
      "total": "1d 00h",
      "fraction": 0.5,
      "percent": 50.0,
      "percent_left": 50.0,
      "elapsed_seconds": 43200,
      "elapsed": "12h 00m",
      "remaining_seconds": 43200,
      "remaining": "12h 00m"
    }
  ]
}
```

Durations are formatted for humans as up to two parts (`1d 00h`, `12h 00m`,
`3m 05s`, `45s`); the `*_seconds` fields are exact and best for machines.
`percent_left` is the complement of `percent`, the value `--percent-left`
would print, so scripts do not have to subtract it themselves.

## Short options

| Short | Long          |
| ----- | ------------- |
| `-j`  | `--json`      |
| `-p`  | `--plain`     |
| `-a`  | `--ascii`     |
| `-c`  | `--countdown` |
| `-e`  | `--elapsed`   |
| `-w`  | `--width`     |
| `-V`  | `--version`   |
| `-h`  | `--help`      |

`--at`, `--until`, `--since`, `--percent`, `--total`, `--precision`,
`--week-start` and `--watch` have no short form.

## Errors and exit codes

- `0` on success, including `Ctrl-C` during `--watch` and a closed pipe
  such as `timeleft --countdown day | head -1`.
- `2` on usage errors: an unknown period, an unparseable `--at`/`--until`/
  `--since`, a
  non-positive `--width`, an invalid `--watch` interval, or `--watch` with
  `--json`. The message goes to stderr, prefixed with `timeleft: error:`.

## Time handling

- Times are local and naive; no timezone database is needed. ISO timestamps
  with `Z` or an explicit offset are converted to local time.
- A period is treated as fully elapsed only when it is over, so its percentage
  stays at `99.9%` until the exact end (e.g. `23:59:59` of a day).
- `--countdown`, `--percent`, `--elapsed` and `--until` print one line per
  requested period, in the order requested.
