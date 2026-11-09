# Development log

Running notes for `timeleft`. Newest entry first. Each entry records what
changed, why, and what is worth doing next, so the project's direction is
readable without digging through commits.

## 2026-11-09

Bootstrap.

- Chose the idea: a zero-dependency CLI that reports the elapsed share and
  remaining time of the current day, week, month, quarter and year.
- Added the package skeleton (`pyproject.toml`, `timeleft/`, `tests/`,
  `LICENSE`, `README.md`, `.gitignore`).
- Implemented period spans in `timeleft/core.py` (weeks start on Monday,
  naive local datetimes, no timezone database needed).
- Implemented `format_duration`, `render_bar` and `build_report`.
- Implemented the CLI: period selection, `--at`, `--json`, `--plain`,
  `--width`, `--version`.
- Wrote unittest suites for core arithmetic and the CLI.
- Verified with `python3 -m unittest discover -s tests -v`.

Next ideas: business-day mode (`--business`), a short `~/.config/timeleft`
file for defaults, shell prompt helper, and a `--compact` single-line output.
