#!/usr/bin/env python3
"""Fetch CPI-U component indexes from the BLS Public Data API.

Reads the item hierarchy from ../series.json and downloads, for every row:
  * CUSR0000<code>  seasonally adjusted index  -> MoM % (2 decimals), 3m/6m annualized
  * CUUR0000<code>  not seasonally adjusted    -> YoY % (matches the official 12-month change)

Indexes are published to 3 decimals; the BLS news release rounds percent changes
to 1 decimal. This script keeps the 3-decimal indexes so the dashboard can show the
"unrounded" 2-decimal MoM that markets watch.

Usage:
    python3 fetch_cpi.py [--start 2025-01] [--out data/cpi.json]

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
SA, NSA = "CUSR0000", "CUUR0000"


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


def to_levels(data: list, base: str) -> dict[str, float]:
    levels = {}
    for d in data:
        if not d["period"].startswith("M") or d["period"] == "M13":
            continue
        ym = f'{d["year"]}-{d["period"][1:]}'
        if ym < base or d["value"] in ("-", ""):
            continue
        try:
            levels[ym] = float(d["value"])
        except ValueError:
            continue
    return dict(sorted(levels.items()))


def month_back(d: dt.date, n: int) -> dt.date:
    for _ in range(n):
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01", help="first month to show MoM for (YYYY-MM)")
    ap.add_argument("--out", default="data/cpi.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    base = month_back(start, 12)  # 12 months back so YoY and 6m annualized exist from `start`
    end_year = dt.date.today().year

    rows = load_rows()
    key = os.environ.get("BLS_API_KEY") or None
    ids = [SA + r["code"] for r in rows] + [NSA + r["code"] for r in rows]
    print(f"Fetching {len(ids)} CPI series {base:%Y-%m}..present ({'v2 with key' if key else 'v1, no key'})", file=sys.stderr)
    raw = fetch(ids, base.year, end_year, key)

    missing, nsa_only = [], []
    for r in rows:
        r["sa"] = to_levels(raw.get(SA + r["code"], []), f"{base:%Y-%m}")
        r["nsa"] = to_levels(raw.get(NSA + r["code"], []), f"{base:%Y-%m}")
        if not r["sa"] and not r["nsa"]:
            missing.append(r["code"])
        elif not r["sa"]:
            nsa_only.append(r["code"])

    if missing:
        print(f"WARNING: no data for {len(missing)} items: {', '.join(missing)}", file=sys.stderr)
    if nsa_only:
        print(f"NOTE: no seasonally adjusted series for: {', '.join(nsa_only)} (MoM falls back to NSA)", file=sys.stderr)

    out = {
        "source": "U.S. Bureau of Labor Statistics, CPI-U, U.S. city average (MoM: seasonally adjusted; YoY: not seasonally adjusted)",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "start": f"{start:%Y-%m}",
        "rows": rows,
        "missing": missing,
        "nsa_only": nsa_only,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    latest = max((m for r in rows for m in r["sa"]), default="n/a")
    print(f"Wrote {path} (latest month {latest})", file=sys.stderr)

    # Quick console summary of the latest month, 2-decimal MoM.
    for r in rows:
        s = r["sa"] or r["nsa"]
        if latest in s:
            prev = month_back(dt.date.fromisoformat(latest + "-01"), 1).strftime("%Y-%m")
            if prev in s:
                mom = (s[latest] / s[prev] - 1) * 100
                print(f"  {'  ' * r['level']}{r['en'][:48]:<48} {mom:+.2f}%", file=sys.stderr)


if __name__ == "__main__":
    main()
