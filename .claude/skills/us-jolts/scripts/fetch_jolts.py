#!/usr/bin/env python3
"""Fetch JOLTS (Job Openings and Labor Turnover Survey) data from the BLS Public Data API.

Reads the industry hierarchy and data elements from ../series.json, downloads seasonally
adjusted levels (thousands) and rates (%) for every industry x element, plus the CPS number
of unemployed (LNS13000000) for the unemployed-per-opening ratio, and writes a JSON file that
build_dashboard.py turns into the interactive web page.

Usage:
    python3 fetch_jolts.py [--start 2025-01] [--annual-from 2019] [--out jolts/data/jolts.json]

All months from January of (--annual-from - 1) are kept, so the yearly columns (annual
averages and Dec-to-Dec changes) and the 3-month averages from --start on can be computed.

API key:
    Set BLS_API_KEY (free: https://data.bls.gov/registrationEngine/).
    With a key the v2 API is used (50 series/request, 500 requests/day): 6 requests.
    Without a key the v1 API is used (25 series/request, 25 requests/day): 12 requests,
    and v1 only returns up to 10 years.

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
UNEMPLOYED = "LNS13000000"   # CPS unemployed, SA, thousands


def series_id(industry: str, element: str, kind: str) -> str:
    """kind: 'L' = level (thousands), 'R' = rate (%)."""
    return f"JTS{industry}00" "00000" "00" f"{element}{kind}"


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
            if "Catalog Data" not in m:   # harmless notice for series without catalog metadata
                print(f"  BLS: {m}", file=sys.stderr)
        for s in res["Results"]["series"]:
            out[s["seriesID"]] = s["data"]
    return out


def parse(data: list, first: str) -> tuple[dict, list]:
    values, prelim = {}, []
    for d in data:
        if not d["period"].startswith("M") or d["period"] == "M13":
            continue
        ym = f'{d["year"]}-{d["period"][1:]}'
        if ym < first or d["value"] in ("-", ""):
            continue
        values[ym] = float(d["value"])
        if any(fn.get("code") == "P" for fn in d.get("footnotes", []) if fn):
            prelim.append(ym)
    return dict(sorted(values.items())), sorted(prelim)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01", help="first month to show in the monthly columns (YYYY-MM)")
    ap.add_argument("--annual-from", type=int, default=2019, help="first year to show in the yearly columns")
    ap.add_argument("--out", default="jolts/data/jolts.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    first_year = min(start.year - 1, args.annual_from - 1)
    first = f"{first_year}-01"
    end_year = dt.date.today().year

    cfg = json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))
    rows, elements = cfg["rows"], cfg["elements"]
    ids = [series_id(r["code"], e["code"], k) for r in rows for e in elements for k in "LR"] + [UNEMPLOYED]
    key = os.environ.get("BLS_API_KEY") or None
    print(f"Fetching {len(ids)} series {first_year}..present ({'v2 with key' if key else 'v1, no key'})", file=sys.stderr)
    raw = fetch(ids, first_year, end_year, key)

    missing, prelim_all = [], set()
    for r in rows:
        r["data"] = {}
        for e in elements:
            entry = {}
            for k, name in (("L", "level"), ("R", "rate")):
                sid = series_id(r["code"], e["code"], k)
                vals, prelim = parse(raw.get(sid, []), first)
                if not vals:
                    missing.append(sid)
                entry[name] = vals
                prelim_all.update(prelim)
            r["data"][e["code"]] = entry
    unemployed, _ = parse(raw.get(UNEMPLOYED, []), first)
    if not unemployed:
        missing.append(UNEMPLOYED)
    if missing:
        print(f"WARNING: no data for {len(missing)} series: {', '.join(missing)}", file=sys.stderr)

    out = {
        "source": "U.S. Bureau of Labor Statistics, Job Openings and Labor Turnover Survey (JOLTS), seasonally adjusted; unemployed from CPS (LNS13000000)",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "start": f"{start:%Y-%m}",
        "annual_from": args.annual_from,
        "elements": elements,
        "rows": rows,
        "unemployed": unemployed,
        "prelim": sorted(prelim_all),
        "missing": missing,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = rows[0]["data"]
    latest = max(total["JO"]["level"], default="n/a")
    print(f"Wrote {path} (latest month {latest})", file=sys.stderr)
    if latest != "n/a":
        for e in elements:
            d = total[e["code"]]
            print(f"  {e['en']:<24} {d['level'].get(latest, float('nan')):>8,.0f}k  rate {d['rate'].get(latest, float('nan')):.1f}%", file=sys.stderr)
        u = unemployed.get(latest)
        if u:
            print(f"  Unemployed per opening   {u / total['JO']['level'][latest]:.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
