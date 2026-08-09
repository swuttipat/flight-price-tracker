# Flight Price Tracker — from Bangkok

A decision-support dashboard for flight prices on 13 routes out of **BKK**, fed by a
manually-collected dataset. Answers two questions:

- **When to book** a known trip (is the fare dropping — buy now or wait?)
- **When to fly** for a flexible trip (which departure date/month is cheapest?)

## Routes (all from BKK)

- Thailand: HKT, CNX, KBV, CEI
- China: PVG, PEK, CAN
- Japan: NRT, HND, KIX
- Vietnam: SGN, HAN, DAD

Edit the `ROUTES` list in `collector.py` to change them.

## Architecture (3 layers)

1. **Collect** — `collector.py` writes two dated files to `data/raw/`:
   - `YYYY-MM-DD-prices.csv` — book-timing: one cheapest fare per route (daily snapshot).
   - `YYYY-MM-DD-calendar.csv` — fly-timing: cheapest fare per departure date (~180 days).
2. **Pipeline** — `pipeline.py` merges raw files into `data/processed/`:
   `prices_master.csv`, `calendar_latest.csv`, and `app_data.js` (the dashboard's data).
3. **Dashboard** — `dashboard/index.html` (Chart.js). Double-click to open. Two tabs:
   - *When to book*: price-over-time with all-time low/high/median band, a **deal score**
     (today vs its own history), and a 7-day trend.
   - *When to fly*: price by departure date with the cheapest day highlighted, plus a
     cheapest-by-month table.

## Run it (manual)

Double-click **`scripts/run.bat`**, or run from the `scripts` folder:

```
py collector.py --real     # collect today (book + calendar). Omit --real for sample data.
py pipeline.py             # rebuild the dashboard data
```
Then open `dashboard/index.html`.

Tip: `py collector.py --check` tests the API and prints today's cheapest per route.

## Real prices — Travelpayouts

Free Data API (Aviasales aggregator). Setup once:

```
setx TRAVELPAYOUTS_TOKEN "your_token"   (reopen terminal)
py collector.py --check
```

Notes:
- Returns ONE cheapest fare per route (the aggregator's), not per-OTA. A true
  Agoda/Trip/Traveloka split would need a paid source (SerpApi Google Flights).
- Optional: set `TP_DEPART_MONTH=YYYY-MM` to fix the scan to one month (comparable day-to-day).
- The Cowork sandbox blocks the API, so `--real` must run on your own computer. Sample mode works anywhere.

## Rules
- `data/raw/` is append-only — don't edit or delete past daily files.
- Re-run `pipeline.py` after every collection before opening the dashboard.
