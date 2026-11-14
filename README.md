# timeleft

[![CI](https://github.com/bekka0668/timeleft/actions/workflows/ci.yml/badge.svg)](https://github.com/bekka0668/timeleft/actions/workflows/ci.yml)

How much of the day, week, month, quarter or year is left? `timeleft` answers
that in one line, with a progress bar, so you can see where you are in the
current period at a glance.

```console
$ timeleft
day     [████████████████░░░░░░░░░]  66.7%  8h 00m left
week    [████████████████████░░░░░]  81.0%  1d 08h left
month   [███████████░░░░░░░░░░░░░░]  45.6%  16d 08h left
quarter [████████████░░░░░░░░░░░░░]  48.6%  47d 08h left
year    [█████████████████████░░░░]  87.0%  47d 08h left
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

### **[USAGE.md](docs/USAGE.md)**.

## Development

```console
$ python3 -m unittest discover -s tests -v
```

## License

MIT, see [LICENSE](LICENSE).
