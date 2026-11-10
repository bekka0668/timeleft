# timeleft

[![CI](https://github.com/bekka0668/timeleft/actions/workflows/ci.yml/badge.svg)](https://github.com/bekka0668/timeleft/actions/workflows/ci.yml)

How much of the day, week, month, quarter or year is left? `timeleft` answers
that in one line, with a progress bar, so you can see where you are in the
current period at a glance.

```console
$ timeleft
day     [███████████████░░░░░░░░░]  69.8%   7h 16m left
week    [████████████░░░░░░░░░░░░]  48.6%   3d 10h left
month   [████████░░░░░░░░░░░░░░░░]  31.4%   20d 09h left
year    [██████████████████████░░]  85.4%   53d 02h left
```

## Why

Deadlines, goals and habits are easier to reason about when you can see the
share of the period that is already gone. `timeleft` is a zero-dependency
Python CLI for exactly that, suitable for a shell prompt, a status bar or a
`cron` job.

## Install

```console
$ pipx install .
# or, without installing anything:
$ python3 -m timeleft
```

## Usage

```console
$ timeleft                 # all periods
$ timeleft week month      # only the periods you ask for
$ timeleft --json          # machine readable output
$ timeleft day --at 2026-11-09T12:00   # evaluate at a fixed moment
$ timeleft day --at +90m               # or look 90 minutes ahead of now
$ timeleft day --at +2h30m             # offsets can be combined
$ timeleft day --at 18:30              # or at a clock time today
$ timeleft day --at tomorrow           # now, today, tomorrow, yesterday
$ timeleft --width 40 --plain          # wider bar, no bar
$ timeleft --ascii                     # ASCII bar for terminals without block glyphs
$ timeleft week --week-start sunday    # Sunday-based weeks (any weekday works)
$ timeleft day --countdown             # just "6h 58m" for a status bar
$ timeleft --percent                   # just the percentages
$ timeleft --elapsed                   # just the time already spent
```

Periods: `day`, `week`, `month`, `quarter`, `year`, or just their first
letter (`d`, `w`, `m`, `q`, `y`).

Weeks start on Monday by default. Times are local time and naive (no timezone
database is required). The bar switches to ASCII automatically when the output
encoding cannot represent the block glyphs.

## Development

```console
$ python3 -m unittest discover -s tests -v
```

## License

MIT, see [LICENSE](LICENSE).
