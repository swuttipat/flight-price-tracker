#!/usr/bin/env python3
"""Pipeline: merge raw daily files into clean datasets for the dashboard.

Reads
  data/raw/*-prices.csv      (book-timing daily snapshots, append-only)
  data/raw/*-calendar.csv    (fly-timing calendars; ALL snapshots are merged,
                              keeping the most-recent observed price per
                              departure date, sample snapshots excluded)
Writes
  data/processed/prices_master.csv     full book-timing history
  data/processed/calendar_latest.csv   merged fly-timing view (freshest price/day)
  data/processed/app_data.js           window.FLIGHT_DATA for the dashboard
  data/processed/price_change_log.csv  per-route daily move + trailing-window position
"""
from __future__ import annotations
import csv
import glob
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "..", "data", "raw")
OUT_DIR = os.path.join(HERE, "..", "data", "processed")

# Exclude departures within this many days of the scrape date. Same-day and
# very-near-term walk-up fares are extreme outliers and distort the dashboard.
MIN_LEAD_DAYS = 2

# Snapshots collected in SAMPLE mode (synthetic, not real fares). Excluded from
# every merge so generated data never reaches the dashboard. Add a date here if
# you ever run the collector without --real again.
EXCLUDE_SNAPSHOTS = {"2026-06-09"}

COUNTRY_ORDER = {"Thailand": 0, "China": 1, "Japan": 2, "Vietnam": 3}
PRICE_FIELDS = ["date", "route", "origin", "destination", "country", "city", "price", "currency"]
CAL_FIELDS = ["date", "route", "origin", "destination", "country", "city", "departure_date", "price", "currency"]

# Change-log window: 30 OBSERVATIONS, not 30 calendar days. Collection can skip a
# day (API outage, disabled workflow), and a gap shouldn't silently shrink the
# window it's compared against.
CHANGE_WINDOW = 30
CHANGE_MIN_FOR_FLAG = 7      # don't call something a "low" on the second day of data
CHANGE_FIELDS = ["date", "route", "city", "price", "prev_price", "delta", "delta_pct",
                 "window_n", "low", "high", "pct_rank", "flag"]


def _date_ok(s):
    try:
        datetime.strptime(s, "%Y-%m-%d"); return True
    except (ValueError, TypeError):
        return False


def _snap_of(path):
    """Snapshot (collection) date taken from a raw filename: YYYY-MM-DD-*.csv."""
    return os.path.basename(path)[:10]


def load_book():
    rows = []
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*-prices.csv"))):
        if _snap_of(path) in EXCLUDE_SNAPSHOTS:
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    if not _date_ok(r["date"]) or int(r["price"]) <= 0:
                        continue
                    rows.append({k: r[k] for k in PRICE_FIELDS} | {"price": int(r["price"])})
                except (KeyError, ValueError, TypeError):
                    continue
    return rows


def load_merged_calendar():
    """Merge every calendar snapshot (sample snapshots excluded) into one row per
    (route, departure_date), keeping the MOST RECENTLY OBSERVED price.

    Why merge instead of using only the newest file: the raw calendars are
    append-only daily snapshots. Taking only the latest file discards ~90% of the
    fares already collected and leaves the chart full of gaps whenever that one
    snapshot is sparse. Merging backfills those gaps with the freshest price we
    have actually seen for each departure date. Near-term/past departures are
    dropped relative to the freshest snapshot date (the effective "today").
    """
    files = [p for p in sorted(glob.glob(os.path.join(RAW_DIR, "*-calendar.csv")))
             if _snap_of(p) not in EXCLUDE_SNAPSHOTS]
    if not files:
        return [], None
    latest_snap = _snap_of(files[-1])
    latest_date = datetime.strptime(latest_snap, "%Y-%m-%d") if _date_ok(latest_snap) else None

    best = {}   # (route, departure_date) -> (snapshot_date, row)
    for path in files:
        snap = _snap_of(path)
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            try:
                if not _date_ok(r["departure_date"]) or int(r["price"]) <= 0:
                    continue
                # drop near-term / past departures relative to the freshest snapshot
                if latest_date is not None:
                    lead = (datetime.strptime(r["departure_date"], "%Y-%m-%d") - latest_date).days
                    if lead < MIN_LEAD_DAYS:
                        continue
                key = (r["route"], r["departure_date"])
                prev = best.get(key)
                # keep the most recently observed price; on a tie, the lower price
                if (prev is None or snap > prev[0]
                        or (snap == prev[0] and int(r["price"]) < int(prev[1]["price"]))):
                    best[key] = (snap, {k: r[k] for k in CAL_FIELDS} | {"price": int(r["price"])})
            except (KeyError, ValueError, TypeError):
                continue
    return [v[1] for v in best.values()], latest_snap


def book_proxy_from_calendar():
    """Per snapshot day, the cheapest calendar fare per route. A real proxy for
    that day's 'cheapest available fare' (the book metric), used only to backfill
    routes the dedicated book endpoint never returned (the pricey China/Japan
    routes the cheap-fare call skips). Sample snapshots excluded.
    """
    by = {}  # (route, snap) -> book-shaped row holding the day's min price
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*-calendar.csv"))):
        snap = _snap_of(path)
        if snap in EXCLUDE_SNAPSHOTS:
            continue
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            try:
                if not _date_ok(r["departure_date"]) or int(r["price"]) <= 0:
                    continue
                price = int(r["price"])
                key = (r["route"], snap)
                if key not in by or price < by[key]["price"]:
                    by[key] = {"date": snap, "route": r["route"], "origin": r["origin"],
                               "destination": r["destination"], "country": r["country"],
                               "city": r["city"], "price": price, "currency": r["currency"]}
            except (KeyError, ValueError, TypeError):
                continue
    return list(by.values())


def dedupe_book(rows):
    """Lowest price per (date, route)."""
    best = {}
    for r in rows:
        key = (r["date"], r["route"])
        if key not in best or r["price"] < best[key]["price"]:
            best[key] = r
    return list(best.values())


def dedupe_calendar(rows):
    """Lowest price per (route, departure_date)."""
    best = {}
    for r in rows:
        key = (r["route"], r["departure_date"])
        if key not in best or r["price"] < best[key]["price"]:
            best[key] = r
    return list(best.values())


def build_change_log(book):
    """Per route per day: the move since the last observation, and where today's
    price sits inside its own trailing window.

    This is the record behind "is it dropping - book now or wait?". Regenerated
    in full from the book series rather than appended, so a re-run can't duplicate
    rows and a corrected raw file flows straight through.
    """
    by_route = {}
    for r in book:
        by_route.setdefault(r["route"], []).append(r)

    out = []
    for rows in by_route.values():
        rows = sorted(rows, key=lambda x: x["date"])
        for i, r in enumerate(rows):
            price = r["price"]
            window = [x["price"] for x in rows[max(0, i - CHANGE_WINDOW + 1):i + 1]]
            lo, hi = min(window), max(window)
            prev = rows[i - 1]["price"] if i else None

            # share of the window cheaper than today; 0 = cheapest we've seen
            rank = ""
            if len(window) > 1:
                cheaper = sum(1 for p in window[:-1] if p < price)
                rank = round(100.0 * cheaper / (len(window) - 1), 1)

            flag = ""
            if len(window) >= CHANGE_MIN_FOR_FLAG:
                if price == lo:
                    flag = f"low in {len(window)}"
                elif price == hi:
                    flag = f"high in {len(window)}"

            out.append({
                "date": r["date"], "route": r["route"], "city": r["city"], "price": price,
                "prev_price": prev if prev is not None else "",
                "delta": (price - prev) if prev is not None else "",
                "delta_pct": round(100.0 * (price - prev) / prev, 1) if prev else "",
                "window_n": len(window), "low": lo, "high": hi,
                "pct_rank": rank, "flag": flag,
            })
    return sorted(out, key=lambda x: (x["date"], x["route"]))


def build():
    book = load_book()
    book_routes = {r["route"] for r in book}
    # backfill routes the dedicated book endpoint never returned, using each
    # day's cheapest calendar fare as a real proxy for that day's book price
    book += [r for r in book_proxy_from_calendar() if r["route"] not in book_routes]
    book = dedupe_book(book)
    cal, snap = load_merged_calendar()   # merged across all real snapshots
    os.makedirs(OUT_DIR, exist_ok=True)

    # full book-timing CSV
    book_sorted = sorted(book, key=lambda r: (r["route"], r["date"]))
    with open(os.path.join(OUT_DIR, "prices_master.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_FIELDS); w.writeheader(); w.writerows(book_sorted)

    # latest calendar CSV
    cal_sorted = sorted(cal, key=lambda r: (r["route"], r["departure_date"]))
    with open(os.path.join(OUT_DIR, "calendar_latest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAL_FIELDS); w.writeheader(); w.writerows(cal_sorted)

    # per-route change log, derived from the book series
    changes = build_change_log(book)
    with open(os.path.join(OUT_DIR, "price_change_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CHANGE_FIELDS); w.writeheader(); w.writerows(changes)

    # route metadata (ordered by country then city)
    rmeta = {}
    for r in book + cal:
        rmeta.setdefault(r["route"], {
            "route": r["route"], "origin": r["origin"], "destination": r["destination"],
            "country": r["country"], "city": r["city"],
        })
    routes = sorted(rmeta.values(), key=lambda m: (COUNTRY_ORDER.get(m["country"], 9), m["city"]))

    book_by_route, cal_by_route = {}, {}
    for m in routes:
        rt = m["route"]
        book_by_route[rt] = [{"date": r["date"], "price": r["price"]}
                             for r in sorted((x for x in book if x["route"] == rt), key=lambda x: x["date"])]
        cal_by_route[rt] = [{"departure_date": r["departure_date"], "price": r["price"]}
                            for r in sorted((x for x in cal if x["route"] == rt), key=lambda x: x["departure_date"])]

    dates = sorted({r["date"] for r in book})
    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "currency": (book or cal or [{"currency": "THB"}])[0]["currency"],
            "origin": "BKK",
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "calendar_date": snap,
            "n_routes": len(routes),
        },
        "routes": routes,
        "book": book_by_route,
        "calendar": cal_by_route,
    }

    with open(os.path.join(OUT_DIR, "app_data.js"), "w", encoding="utf-8") as f:
        f.write("window.FLIGHT_DATA = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";\n")

    print(f"book rows: {len(book)} over {len(dates)} days | calendar rows: {len(cal)} (snap {snap}) | routes: {len(routes)}")
    flagged = sum(1 for c in changes if c["flag"])
    print(f"change log: {len(changes)} rows, {flagged} flagged")
    print("Wrote prices_master.csv, calendar_latest.csv, app_data.js, price_change_log.csv")


if __name__ == "__main__":
    build()
