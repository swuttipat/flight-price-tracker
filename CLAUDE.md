# CLAUDE.md — flight price tracker

## Goal

A working decision-support dashboard for flights out of Bangkok that answers
"when should I book?" and "when should I fly?" across 13 routes, from an
automatically-collected daily dataset.

## Where this project lives

Canonical copy: `C:\dev\flight-price-tracker`, pushed to
https://github.com/swuttipat/flight-price-tracker (public). Deliberately OUTSIDE
OneDrive — sync corrupts `.git` internals, and it also removes the truncated-file
problem the sandbox used to hit. The old OneDrive copy under
`Travel\flight price tracker` is a frozen pre-automation snapshot; do not edit it.

## Project-Specific Workflow

1. **Collect** — `scripts/collector.py` writes two dated files to `data/raw/` per run:
   `YYYY-MM-DD-prices.csv` (book-timing: cheapest fare per route) and
   `YYYY-MM-DD-calendar.csv` (fly-timing: cheapest fare per departure date, ~180d).
   Sample data by default; `--real` uses the Travelpayouts API.
2. **Pipeline** — `scripts/pipeline.py` merges raw files and writes
   `data/processed/{prices_master.csv, calendar_latest.csv, app_data.js, price_change_log.csv}`.
3. **Dashboard** — `dashboard/index.html` loads `app_data.js`; two tabs
   (When to book / When to fly). Re-run the pipeline before opening it.
4. **Collection is automated.** `.github/workflows/daily-collect.yml` runs steps 1-2
   at 01:00 UTC (08:00 Bangkok) and commits the result. Nothing runs on Max's laptop.
5. `scripts/run.bat` now only does `git pull` — it no longer calls the API.

## Project-Specific Rules

- `data/raw/` is append-only. Never edit or delete past daily files.
- Routes are defined in the `ROUTES` list in `collector.py` (origin fixed = BKK). Currency THB.
- Book-timing schema: `date,route,origin,destination,country,city,price,currency`.
- Fly-timing schema adds `departure_date`. Don't break either schema — the dashboard depends on it.
- Real source = Travelpayouts (one aggregator price per route, not per-OTA). To go fully
  per-OTA would need a paid source (SerpApi). Keep the same output schema when changing sources.
- GitHub Actions is the SOLE writer of `data/raw/`. Don't collect locally on a day the
  workflow already ran — you'll collide with that day's snapshot. To collect by hand
  anyway: `py scripts\collector.py --real` then `py scripts\pipeline.py`, and commit.
- The `TRAVELPAYOUTS_TOKEN` lives in GitHub repo secrets and in Max's Windows user env.
  Never commit it, never print it into a transcript.
- `price_change_log.csv` is regenerated in full each run, never appended — a re-run must
  not duplicate rows. Its window is 30 OBSERVATIONS, not 30 calendar days.
- Exclude sample snapshots from the pipeline (EXCLUDE_SNAPSHOTS in pipeline.py); keep sample and real data separate. The fly view merges all real calendar snapshots, not just the latest.
