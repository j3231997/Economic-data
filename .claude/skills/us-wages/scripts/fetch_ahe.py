#!/usr/bin/env python3
"""Fetch CES average hourly earnings (all employees) from the BLS Public Data API.

Reads the industry hierarchy from ../series.json, downloads seasonally adjusted average
hourly earnings of all employees (dollars, 2 decimals) for every row, and writes a JSON file
that build_dashboard.py turns into the interactive web page. MoM % is computed in the page
from the dollar levels, so it carries 2 decimals instead of the news release's 1.

Usage:
    python3 fetch_ahe.py [--start 2025-01] [--annual-from 2019] [--out wages/data/ahe.json]

All months from January of (--annual-from - 1) are kept (and at least 13 months before
--start), so YoY, 3-month averages and the Dec-to-Dec yearly columns can be computed.

API key:
    Set BLS_API_KEY (free: https://data.bls.gov/registrationEngine/).
    With a key the v2 API is used (50 series/request): 2 requests.
    Without a key the v1 API is used (25 series/request, 25 requests/day): 3 requests.

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
API_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
API_V2 = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def post(url: str, payload: dict, retries: int = 3) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  network error ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch(series_ids: list[str], start_year: int, end_year: int, key: str | None) -> dict[str, list]:
    url, batch = (API_V2, 50) if key else (API_V1, 25)
    out: dict[str, list] = {}
    for i in range(0, len(series_ids), batch):
        chunk = series_ids[i : i + batch]
        payload = {"seriesid": chunk, "startyear": str(start_year), "endyear": str(end_year)}
        if key:
            payload["registrationkey"] = key
        print(f"  request {i // batch + 1}: {len(chunk)} series", file=sys.stderr)
        res = post(url, payload)
        if res.get("status") != "REQUEST_SUCCEEDED":
            msg = " | ".join(res.get("message", [])) or res.get("status")
            raise SystemExit(f"BLS API error: {msg}")
        for m in res.get("message", []):
            print(f"  BLS: {m}", file=sys.stderr)
        for s in res["Results"]["series"]:
            out[s["seriesID"]] = s["data"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01", help="first month to show in the monthly columns (YYYY-MM)")
    ap.add_argument("--annual-from", type=int, default=2019, help="first year to show the Dec-to-Dec % change for")
    ap.add_argument("--out", default="wages/data/ahe.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    first_year = min(start.year - 2, args.annual_from - 1)   # YoY of the 3-month window needs >12 months back
    first = f"{first_year}-01"
    end_year = dt.date.today().year

    rows = json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]
    key = os.environ.get("BLS_API_KEY") or None
    print(f"Fetching {len(rows)} AHE series {first_year}..present ({'v2 with key' if key else 'v1, no key'})", file=sys.stderr)
    raw = fetch([r["id"] for r in rows], first_year, end_year, key)

    missing = []
    for r in rows:
        levels, prelim = {}, []
        for d in raw.get(r["id"], []):
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            ym = f'{d["year"]}-{d["period"][1:]}'
            if ym < first or d["value"] in ("-", ""):
                continue
            levels[ym] = float(d["value"])
            if any(fn.get("code") == "P" for fn in d.get("footnotes", []) if fn):
                prelim.append(ym)
        if not levels:
            missing.append(r["id"])
        r["levels"] = dict(sorted(levels.items()))
        r["prelim"] = sorted(prelim)
    if missing:
        print(f"WARNING: no data for {len(missing)} series: {', '.join(missing)}", file=sys.stderr)

    out = {
        "source": "U.S. Bureau of Labor Statistics, Current Employment Statistics (CES), average hourly earnings of all employees, seasonally adjusted, dollars",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "start": f"{start:%Y-%m}",
        "annual_from": args.annual_from,
        "rows": rows,
        "missing": missing,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    total = rows[0]["levels"]
    if total:
        months = sorted(total)
        latest = months[-1]
        print(f"Wrote {path} (latest month {latest})", file=sys.stderr)
        print("  Total private AHE, last 6 months (MoM % 2 decimals / official 1 decimal):", file=sys.stderr)
        for m, p in list(zip(months[1:], months[:-1]))[-6:]:
            g = (total[m] / total[p] - 1) * 100
            print(f"    {m}  ${total[m]:.2f}  {g:+.2f}%  ({g:+.1f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
