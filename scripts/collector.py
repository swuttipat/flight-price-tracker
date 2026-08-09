#!/usr/bin/env python3
"""Daily flight-price collector (Bangkok hub).

Two datasets per run, written to data/raw/ :
  * BOOK-TIMING  ->  YYYY-MM-DD-prices.csv
      one row per route = today's cheapest fare snapshot.
      Used to answer "is the price dropping - buy now or wait?"
      schema: date,route,origin,destination,country,city,price,currency
  * FLY-TIMING   ->  YYYY-MM-DD-calendar.csv
      cheapest fare per DEPARTURE date over the horizon.
      Used to answer "which date/month is cheapest to fly?"
      schema: date,route,origin,destination,country,city,departure_date,price,currency

Sources:
  * SAMPLE (default)    -> realistic generated data, no network.
  * REAL  (--real)      -> Travelpayouts (Aviasales) Data API.

Setup for REAL mode:
  1. Free account at travelpayouts.com -> copy your Data API token.
  2. setx TRAVELPAYOUTS_TOKEN "your_token"   (reopen terminal)
  3. py collector.py --real
"""
from __future__ import annotations
import csv
import json
import os
import random
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "..", "data", "raw")

CURRENCY = "THB"
ORIGIN = "BKK"
HORIZON_DAYS = 180       # fly-timing calendar look-ahead

# route catalogue: dest -> (country, city, sample baseline THB one-way)
ROUTES = [
    ("HKT", "Thailand", "Phuket",            2200),
    ("CNX", "Thailand", "Chiang Mai",        1300),
    ("KBV", "Thailand", "Krabi",             1600),
    ("CEI", "Thailand", "Chiang Rai",        1500),
    ("PVG", "China",    "Shanghai",          7000),
    ("PEK", "China",    "Beijing",           8000),
    ("CAN", "China",    "Guangzhou",         5500),
    ("NRT", "Japan",    "Tokyo (Narita)",    9500),
    ("HND", "Japan",    "Tokyo (Haneda)",   10000),
    ("KIX", "Japan",    "Osaka",             9000),
    ("SGN", "Vietnam",  "Ho Chi Minh City",  3800),
    ("HAN", "Vietnam",  "Hanoi",             4200),
    ("DAD", "Vietnam",  "Da Nang",           4500),
]

PRICE_FIELDS = ["date", "route", "origin", "destination", "country", "city", "price", "currency"]
CAL_FIELDS = ["date", "route", "origin", "destination", "country", "city", "departure_date", "price", "currency"]

# --- Travelpayouts config ---
TP_CHEAP = "https://api.travelpayouts.com/v1/prices/cheap"
TP_CALENDAR = "https://api.travelpayouts.com/v1/prices/calendar"
TP_TOKEN_ENV = "TRAVELPAYOUTS_TOKEN"
TP_DEPART_MONTH = os.environ.get("TP_DEPART_MONTH", "")   # "YYYY-MM" or blank


# =====================================================================
# SAMPLE MODE
# =====================================================================
def _seasonal(dep: date) -> float:
    # weekends pricier, mid-week cheaper; gentle monthly wave
    wd = {0: 0.97, 1: 0.92, 2: 0.92, 3: 0.98, 4: 1.10, 5: 1.06, 6: 1.12}[dep.weekday()]
    month_wave = 1.0 + 0.05 * ((dep.month % 12) / 12.0 - 0.5)
    return wd * month_wave


def sample_book_row(dest, country, city, base, the_day) -> dict:
    # wandering daily snapshot around the baseline (seed by route+day for stability)
    rnd = random.Random(hash((dest, the_day.toordinal())) & 0xffffffff)
    walk = 1.0 + 0.10 * (rnd.random() - 0.5) + 0.04 * ((the_day.toordinal() % 7) - 3) / 3.0
    price = base * max(0.8, min(1.25, walk)) * rnd.uniform(0.97, 1.03)
    return {
        "date": the_day.isoformat(), "route": f"{ORIGIN}-{dest}",
        "origin": ORIGIN, "destination": dest, "country": country, "city": city,
        "price": int(round(price / 10) * 10), "currency": CURRENCY,
    }


def sample_calendar_rows(dest, country, city, base, the_day) -> list:
    rows = []
    for i in range(HORIZON_DAYS):
        dep = the_day + timedelta(days=i + 3)
        rnd = random.Random(hash((dest, dep.toordinal())) & 0xffffffff)
        price = base * _seasonal(dep) * rnd.uniform(0.94, 1.10)
        rows.append({
            "date": the_day.isoformat(), "route": f"{ORIGIN}-{dest}",
            "origin": ORIGIN, "destination": dest, "country": country, "city": city,
            "departure_date": dep.isoformat(),
            "price": int(round(price / 10) * 10), "currency": CURRENCY,
        })
    return rows


def generate_book(the_day) -> list:
    return [sample_book_row(d, c, city, b, the_day) for (d, c, city, b) in ROUTES]


def generate_calendar(the_day) -> list:
    out = []
    for (d, c, city, b) in ROUTES:
        out += sample_calendar_rows(d, c, city, b, the_day)
    return out


# =====================================================================
# REAL MODE (Travelpayouts)
# =====================================================================
def _token() -> str:
    tok = os.environ.get(TP_TOKEN_ENV)
    if not tok:
        raise RuntimeError(f"Set your token first:  setx {TP_TOKEN_ENV} \"your_token\"")
    return tok


def _get_json(endpoint, params, token):
    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-access-token": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def real_cheapest(dest, token):
    params = {"origin": ORIGIN, "destination": dest, "currency": CURRENCY.lower()}
    if TP_DEPART_MONTH:
        params["depart_date"] = TP_DEPART_MONTH
    p = _get_json(TP_CHEAP, params, token)
    if not p.get("success"):
        return None
    offers = p.get("data", {}).get(dest, {})
    prices = [int(v["price"]) for v in offers.values() if v.get("price")]
    return min(prices) if prices else None


def real_calendar(dest, token):
    """Cheapest price per departure date across the next 6 months."""
    months = []
    if TP_DEPART_MONTH:
        months = [TP_DEPART_MONTH]
    else:
        base = date.today().replace(day=1)
        for k in range(6):
            m = (base.month - 1 + k) % 12 + 1
            y = base.year + (base.month - 1 + k) // 12
            months.append(f"{y:04d}-{m:02d}")
    by_date = {}
    for mon in months:
        params = {"origin": ORIGIN, "destination": dest, "currency": CURRENCY.lower(),
                  "calendar_type": "departure_date", "depart_date": mon}
        try:
            p = _get_json(TP_CALENDAR, params, token)
        except Exception as e:
            print(f"  ! {ORIGIN}-{dest} calendar {mon}: {e}")
            continue
        if not p.get("success"):
            continue
        for k, v in p.get("data", {}).items():
            dep = k[:10]
            price = v.get("price") if isinstance(v, dict) else v
            if price:
                price = int(price)
                if dep not in by_date or price < by_date[dep]:
                    by_date[dep] = price
    return by_date


def fetch_real_book(the_day) -> list:
    token = _token()
    rows = []
    for (d, c, city, b) in ROUTES:
        try:
            price = real_cheapest(d, token)
        except Exception as e:
            print(f"  ! {ORIGIN}-{d}: {e}")
            continue
        if not price:
            print(f"  ! {ORIGIN}-{d}: no cheap fare, skipped")
            continue
        rows.append({"date": the_day.isoformat(), "route": f"{ORIGIN}-{d}",
                     "origin": ORIGIN, "destination": d, "country": c, "city": city,
                     "price": price, "currency": CURRENCY})
    if not rows:
        raise RuntimeError("No fares collected (check token/network).")
    return rows


def fetch_real_calendar(the_day) -> list:
    token = _token()
    rows = []
    for (d, c, city, b) in ROUTES:
        cal = real_calendar(d, token)
        for dep, price in sorted(cal.items()):
            rows.append({"date": the_day.isoformat(), "route": f"{ORIGIN}-{d}",
                         "origin": ORIGIN, "destination": d, "country": c, "city": city,
                         "departure_date": dep, "price": price, "currency": CURRENCY})
    return rows


# =====================================================================
# IO
# =====================================================================
def _write(path, fields, rows):
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def collect(the_day=None, use_real=False, with_calendar=True):
    the_day = the_day or date.today()
    book = fetch_real_book(the_day) if use_real else generate_book(the_day)
    bp = _write(os.path.join(RAW_DIR, f"{the_day.isoformat()}-prices.csv"), PRICE_FIELDS, book)
    print(f"Wrote {len(book)} book rows -> {os.path.normpath(bp)}")
    if with_calendar:
        cal = fetch_real_calendar(the_day) if use_real else generate_calendar(the_day)
        cp = _write(os.path.join(RAW_DIR, f"{the_day.isoformat()}-calendar.csv"), CAL_FIELDS, cal)
        print(f"Wrote {len(cal)} calendar rows -> {os.path.normpath(cp)}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Collect Bangkok-hub flight prices.")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--real", action="store_true", help="use Travelpayouts instead of sample")
    p.add_argument("--seed-days", type=int, help="backfill N days of sample book-timing")
    p.add_argument("--check", action="store_true", help="test API connectivity, no files")
    a = p.parse_args()
    end = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else date.today()

    if a.check:
        tok = os.environ.get(TP_TOKEN_ENV)
        print("Token present:", bool(tok))
        if tok:
            for (d, c, city, b) in ROUTES:
                try:
                    print(f"  {ORIGIN}-{d} ({city}): {real_cheapest(d, tok)} {CURRENCY}")
                except Exception as e:
                    print(f"  {ORIGIN}-{d}: ERROR {e}")
    elif a.seed_days:
        # backfill book-timing history for N days; one calendar snapshot on the last day
        for i in range(a.seed_days - 1, -1, -1):
            collect(end - timedelta(days=i), use_real=False, with_calendar=(i == 0))
    else:
        collect(end, use_real=a.real, with_calendar=True)
