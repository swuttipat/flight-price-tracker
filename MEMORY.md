# flight price tracker Memory

## Status

- 2026-06-10 — Reworked to a decision-support dashboard. 13 BKK routes, two datasets
  (book-timing + fly-timing), two-tab dashboard. Working on sample data. Real
  collection via Travelpayouts; runs manually on Max's own machine (py launcher).
- 2026-06-28 — Pipeline now MERGES all calendar snapshots into the fly view, keeping
  the most-recent observed price per (route, departure_date), instead of using only
  the latest file. The 2026-06-09 sample snapshot is excluded via EXCLUDE_SNAPSHOTS;
  sample and real data are never mixed.

- 2026-08-09 — Collection MOVED OFF the laptop into GitHub Actions. Repo now lives at
  `C:\dev\flight-price-tracker` (outside OneDrive) and is public at
  github.com/swuttipat/flight-price-tracker. Daily workflow at 01:00 UTC / 08:00 Bangkok.
  Added `price_change_log.csv` and a Claude routine that briefs the day's moves.
  Trigger was the wifi-at-boot race: Task Scheduler at logon fired before the network
  was up. Cloud collection removes the laptop from the loop entirely.

## Key Context

- Goal: help decide WHEN TO BOOK (price trend / deal score) and WHEN TO FLY
  (cheapest departure date/month). Both matter equally to Max.
- Routes (all from BKK): Thailand HKT/CNX/KBV/CEI; China PVG/PEK/CAN;
  Japan NRT/HND/KIX; Vietnam SGN/HAN/DAD. Currency THB.
- Two datasets per collector run:
  - prices.csv  = book-timing, one cheapest fare/route/day (trend over collection date).
  - calendar.csv = fly-timing, cheapest fare per departure date (~180d horizon).
- Pipeline emits app_data.js → window.FLIGHT_DATA {meta, routes, book, calendar}.
- Dashboard tabs: "When to book" (hi/lo/median band + deal-score percentile + 7-day trend)
  and "When to fly" (price-by-departure-date bars, cheapest day, cheapest-by-month table).
- Real source: Travelpayouts Data API. cheap endpoint (book) + calendar endpoint (fly).
  ONE aggregator price per route, not per-OTA. Amadeus free tier dropped (shutdown 2026-07-17).
- The Cowork sandbox is blocked from api.travelpayouts.com (403), but GitHub Actions
  runners are NOT — verified 2026-08-09 against a same-day laptop run: 7 of 8 routes
  returned byte-identical THB prices, the 8th (CEI) drifted 4.1% on ordinary intraday
  movement. No datacenter-IP price discrimination.
- Max's machine: `python` not on PATH, use `py` launcher (Python 3.11.5).
- Execution is AUTOMATED via GitHub Actions. Claude routine
  `trig_017uD7NuSxMA6YzbQn44frUT` reads the change log at 02:00 UTC and writes a briefing.
- KNOWN RISK: GitHub disables scheduled workflows after 60 days of repo inactivity, and
  GITHUB_TOKEN pushes don't reset that timer. A warning email arrives first; a manual
  "Run workflow" click re-arms it.
- Travelpayouts' cheap (book) endpoint returns no fare for the 5 pricey routes PVG, PEK,
  NRT, HND, KIX, so the collector saves no book rows for them. The pipeline backfills their
  book series from each day's cheapest calendar fare (book_proxy_from_calendar). The
  dashboard shows a "no booking history yet" empty state when a route has no book data.

## Working Notes

- Sample seeded: 30 days book history (2026-05-11..06-09) + calendar snapshot 2026-06-09.
- Stale/locked files (OneDrive-locked, sandbox can't remove): data/processed/prices.js,
  prices.json (old single-dataset, unused now); data/raw/2026-06-10-prices.csv (old schema,
  ignored by pipeline). These self-heal / can be deleted on Max's machine.
- collector.py flags: --real, --check, --seed-days N, --date YYYY-MM-DD, env TP_DEPART_MONTH.
