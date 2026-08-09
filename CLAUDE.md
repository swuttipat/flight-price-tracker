# CLAUDE.md — flight price tracker

## Goal

A working decision-support dashboard for flights out of Bangkok that answers
"when should I book?" and "when should I fly?" across 13 routes, from a
manually-collected daily dataset.

## Project-Specific Workflow

1. **Collect** — `scripts/collector.py` writes two dated files to `data/raw/` per run:
   `YYYY-MM-DD-prices.csv` (book-timing: cheapest fare per route) and
   `YYYY-MM-DD-calendar.csv` (fly-timing: cheapest fare per departure date, ~180d).
   Sample data by default; `--real` uses the Travelpayouts API.
2. **Pipeline** — `scripts/pipeline.py` merges raw files and writes
   `data/processed/{prices_master.csv, calendar_latest.csv, app_data.js}`.
3. **Dashboard** — `dashboard/index.html` loads `app_data.js`; two tabs
   (When to book / When to fly). Re-run the pipeline before opening it.
4. Real collection runs on Max's own machine with the `py` launcher (sandbox blocks the API).

## Project-Specific Rules

- `data/raw/` is append-only. Never edit or delete past daily files.
- Routes are defined in the `ROUTES` list in `collector.py` (origin fixed = BKK). Currency THB.
- Book-timing schema: `date,route,origin,destination,country,city,price,currency`.
- Fly-timing schema adds `departure_date`. Don't break either schema — the dashboard depends on it.
- Real source = Travelpayouts (one aggregator price per route, not per-OTA). To go fully
  per-OTA would need a paid source (SerpApi). Keep the same output schema when changing sources.
- Execution is manual; do not re-enable a scheduler without asking.
- Exclude sample snapshots from the pipeline (EXCLUDE_SNAPSHOTS in pipeline.py); keep sample and real data separate. The fly view merges all real calendar snapshots, not just the latest.
