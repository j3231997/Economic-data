#!/usr/bin/env python3
"""Fetch US retail & food services sales (Census Bureau, seasonally adjusted, $ millions).

Reads the kind-of-business hierarchy from ../series.json and downloads:
  * adv rows  - Advance Monthly Retail Trade (MARTS) time-series text files
                https://www.census.gov/retail/marts/www/adv<code>.txt (1992-present, includes the
                advance month; SA levels and seasonal factors).
  * mrts rows - Monthly Retail Trade (MRTS) workbook
                https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx, ADJUSTED block
                (finer kinds of business; one month behind the advance report).
  * the release date of the latest advance report (marts_current.xlsx footnote).

No API key is needed (api.census.gov now requires one, these files do not).

If --out already exists and its latest month differs from the new data, its levels are kept as the
"prior vintage" so the dashboard can show revisions to earlier months.

Usage:
    python3 fetch_retail.py [--start 2025-01] [--out retail/data/retail.json]

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ADV_URL = "https://www.census.gov/retail/marts/www/adv{code}.txt"
MRTS_URL = "https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx"
CURRENT_URL = "https://www.census.gov/retail/marts/www/marts_current.xlsx"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def get(url: str, retries: int = 3) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (economic-data fetcher)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise SystemExit(f"download failed: {url}: {e}")
            wait = 2 ** (attempt + 1)
            print(f"  network error ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def num(s) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None   # "(S)" suppressed, "(NA)", blank


# --- MARTS text files --------------------------------------------------------------------------

def parse_adv(text: str) -> dict[str, float]:
    """SA levels from an adv<code>.txt file: 'YYYY v1 ... v12' rows above 'SEASONAL FACTORS'."""
    levels = {}
    for line in text.split("SEASONAL FACTORS")[0].splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"(19|20)\d\d", parts[0]):
            for i, v in enumerate(parts[1:13]):
                x = num(v)
                if x is not None:
                    levels[f"{parts[0]}-{i + 1:02d}"] = x
    return levels


# --- minimal xlsx reader (stdlib) --------------------------------------------------------------

def col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(blob: bytes, want=lambda name: True) -> dict[str, list[list]]:
    """{sheet name: rows as lists of cell values} for the sheets `want` accepts."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        name = sh.get("name")
        if not want(name):
            continue
        target = rels[sh.get(f"{{{NS['r']}}}id")].lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(path)).iter(f"{{{NS['m']}}}row"):
            vals = []
            for c in row.findall("m:c", NS):
                i = col_index(c.get("r"))
                vals.extend([None] * (i - len(vals) + 1))
                v = c.find("m:v", NS)
                if c.get("t") == "s" and v is not None:
                    vals[i] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    vals[i] = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None:
                    vals[i] = v.text
            rows.append(vals)
        out[name] = rows
    return out


def parse_mrts(blob: bytes, first_year: int) -> dict[str, dict[str, float]]:
    """{NAICS code: {YYYY-MM: SA level}} from the ADJUSTED block of every year sheet >= first_year."""
    sheets = read_xlsx(blob, want=lambda n: n.isdigit() and int(n) >= first_year)
    out: dict[str, dict[str, float]] = {}
    for name, rows in sheets.items():
        # Month header row: cells like "Jan. 2026" (some years add a "TOTAL" column).
        cols = {}
        for r in rows[:10]:
            for i, v in enumerate(r):
                m = re.match(r"([A-Za-z]{3})\.?\s*(\d{4})", str(v or "").strip())
                if m and m.group(1).upper() in MONTHS:
                    cols[i] = f"{m.group(2)}-{MONTHS.index(m.group(1).upper()) + 1:02d}"
            if cols:
                break
        adjusted = False
        for r in rows:
            r = r + [None] * (2 - len(r))
            label = str(r[1] if len(r) > 1 and r[1] is not None else "").strip().upper()
            if label.startswith("ADJUSTED"):
                adjusted = True
                continue
            code = re.sub(r"\s", "", str(r[0] or ""))
            if not adjusted or not re.fullmatch(r"[\d,]+", code):
                continue
            for i, ym in cols.items():
                x = num(r[i]) if i < len(r) else None
                if x is not None:
                    out.setdefault(code, {})[ym] = x
    return out


def release_date(blob: bytes) -> str | None:
    """'October 15, 2026' from the marts_current.xlsx source footnote, as YYYY-MM-DD."""
    try:
        text = " ".join(str(c) for rows in read_xlsx(blob).values() for r in rows for c in r if c)
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return None
    m = re.search(r"Advance Monthly Retail Trade Survey,\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    return dt.datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d") if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01", help="first month to show (YYYY-MM)")
    ap.add_argument("--out", default="retail/data/retail.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    base = f"{start.year - 2}-12"   # 13+ months before `start` for YoY and 3-month changes
    rows = json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]

    adv_rows = [r for r in rows if r.get("adv")]
    print(f"Fetching {len(adv_rows)} MARTS time-series files", file=sys.stderr)
    adv = {}
    for r in adv_rows:
        adv[r["adv"]] = parse_adv(get(ADV_URL.format(code=r["adv"])).decode("latin-1"))
    mrts = {}
    if any(r.get("mrts") for r in rows):
        print("Fetching MRTS workbook (detail kinds of business)", file=sys.stderr)
        mrts = parse_mrts(get(MRTS_URL), start.year - 2)
    released = release_date(get(CURRENT_URL))

    missing = []
    for r in rows:
        if r.get("derived"):
            continue
        src = adv.get(r["adv"], {}) if r.get("adv") else mrts.get(r.get("mrts", ""), {})
        r["levels"] = {m: v for m, v in sorted(src.items()) if m >= base}
        if not r["levels"]:
            missing.append(r["id"])
    if missing:
        print(f"WARNING: no data for: {', '.join(missing)} (check adv/mrts codes in series.json)", file=sys.stderr)

    latest = max((m for r in rows for m in r.get("levels", {}) if r.get("adv")), default=None)
    latest_mrts = max((m for r in rows for m in r.get("levels", {}) if r.get("mrts")), default=None)
    out = {
        "source": "U.S. Census Bureau, Advance Monthly Retail Trade Survey (MARTS) & Monthly Retail Trade Survey (MRTS), "
                  "seasonally adjusted, millions of dollars, not adjusted for price changes",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "released": released,
        "start": f"{start:%Y-%m}",
        "latest": latest,
        "latest_mrts": latest_mrts,
        "rows": rows,
        "missing": missing,
    }

    # Prior vintage: keep the previous release's levels so revisions can be shown. Re-fetching the
    # same release keeps the vintage that was stored before it.
    path = Path(args.out)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("latest") != latest:
            out["prior"] = {"latest": old.get("latest"), "released": old.get("released"),
                            "levels": {r["id"]: r.get("levels", {}) for r in old["rows"] if r.get("levels")}}
        elif old.get("prior"):
            out["prior"] = old["prior"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {path} (advance month {latest}, MRTS detail through {latest_mrts}, released {released})", file=sys.stderr)

    # Quick summary of the latest month (MoM %, 2 decimals).
    by = {r["id"]: r for r in rows}
    def lv(i, m):
        r = by[i]
        if r.get("derived"):
            d = r["derived"]
            vals = [lv(c, m) for c in [d["base"]] + d.get("minus", [])]
            return None if None in vals else vals[0] - sum(vals[1:])
        return r["levels"].get(m)
    prev = f"{latest[:4]}-{int(latest[5:]) - 1:02d}" if latest[5:] != "01" else f"{int(latest[:4]) - 1}-12"
    print(f"\n{latest} MoM % (SA):", file=sys.stderr)
    for r in rows:
        a, b = lv(r["id"], latest), lv(r["id"], prev)
        if a is not None and b:
            print(f"  {'  ' * r['level']}{r['en'][:60]:<62} {100 * (a / b - 1):6.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
