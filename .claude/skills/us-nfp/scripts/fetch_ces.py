#!/usr/bin/env python3
"""Fetch CES (Nonfarm Payroll) employment levels from the BLS Public Data API.

Reads the industry hierarchy from ../series.json, downloads seasonally adjusted
All Employees levels (thousands) for every row, and writes a JSON file that
build_dashboard.py turns into the interactive web page.

Usage:
    python3 fetch_ces.py [--start 2025-01] [--out data/nfp_ces.json]

API key:
    Set BLS_API_KEY (free: https://data.bls.gov/registrationEngine/).
    With a key the v2 API is used (50 series/request, 500 requests/day).
    Without a key the v1 API is used (25 series/request, 25 requests/day).

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


def load_rows() -> list[dict]:
    with open(SKILL_DIR / "series.json", encoding="utf-8") as f:
        return json.load(f)["rows"]


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
    ap.add_argument("--start", default="2025-01", help="first month to show MoM change for (YYYY-MM)")
    ap.add_argument("--out", default="data/nfp_ces.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    # Need 3 months before `start` so MoM and 3-month averages exist from `start` on.
    base = start
    for _ in range(3):
        base = (base - dt.timedelta(days=1)).replace(day=1)
    end_year = dt.date.today().year

    rows = load_rows()
    key = os.environ.get("BLS_API_KEY") or None
    print(f"Fetching {len(rows)} CES series {base:%Y-%m}..present ({'v2 with key' if key else 'v1, no key'})", file=sys.stderr)
    raw = fetch([r["id"] for r in rows], base.year, end_year, key)

    missing = []
    for r in rows:
        levels, prelim = {}, []
        for d in raw.get(r["id"], []):
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            ym = f'{d["year"]}-{d["period"][1:]}'
            if ym < f"{base:%Y-%m}" or d["value"] in ("-", ""):
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
        "source": "U.S. Bureau of Labor Statistics, Current Employment Statistics (CES), seasonally adjusted, all employees, thousands",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "start": f"{start:%Y-%m}",
        "rows": rows,
        "missing": missing,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    latest = max((m for r in rows for m in r["levels"]), default="n/a")
    print(f"Wrote {path} (latest month {latest})", file=sys.stderr)


if __name__ == "__main__":
    main()
