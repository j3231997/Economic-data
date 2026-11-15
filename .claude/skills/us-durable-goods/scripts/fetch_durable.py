#!/usr/bin/env python3
"""Fetch US durable goods new orders and shipments (Census Bureau M3 survey, SA, $ millions).

Reads the industry hierarchy from ../series.json and downloads:
  * full-report history workbooks (1992-present, every published M3 category):
      https://www.census.gov/manufacturing/m3/prel/historical_data/histshts/naics/naicsnop.xlsx  (new orders)
      https://www.census.gov/manufacturing/m3/prel/historical_data/histshts/naics/naicsvsp.xlsx  (shipments)
  * the advance report table https://www.census.gov/manufacturing/m3/adv/table1a.xlsx
    (headline industries and capital goods, latest 3 months). The advance report comes out about
    a week before the full report for the same month; when it is newer than the history files, its
    3 months replace the history values for the rows it covers (the earlier two are revisions).
  * the full report Table 1 (table1p.xlsx), only for its release date.

No API key is needed. If --out already exists and holds a different release, its levels are kept as the
"prior vintage" so the dashboard can show revisions.

Usage:
    python3 fetch_durable.py [--start 2025-01] [--out durable/data/durable.json]

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
BASE = "https://www.census.gov/manufacturing/m3"
HIST_URL = BASE + "/prel/historical_data/histshts/naics/naics{kind}p.xlsx"   # kind: no / vs
ADV_URL = BASE + "/adv/table1a.xlsx"
FULL_URL = BASE + "/prel/table1p.xlsx"
MEASURES = {"NO": "no", "VS": "vs"}   # data-type suffix -> history workbook kind
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


# --- minimal xlsx reader (stdlib) --------------------------------------------------------------

def col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(blob: bytes) -> list[list[list]]:
    """Rows (lists of cell values) of every sheet, in workbook order."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = []
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
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
        out.append(rows)
    return out


# --- parsers -----------------------------------------------------------------------------------

def parse_history(blob: bytes) -> dict[str, dict[str, float]]:
    """{series code: {YYYY-MM: value}} from a history workbook: rows 'CODE, YYYY, Jan..Dec'."""
    out: dict[str, dict[str, float]] = {}
    for rows in read_xlsx(blob):
        for r in rows:
            if len(r) < 3 or not r[0] or not re.fullmatch(r"(19|20)\d\d", str(r[1] or "")):
                continue
            for i, v in enumerate(r[2:14]):
                x = num(v)
                if x is not None:
                    out.setdefault(str(r[0]).strip(), {})[f"{r[1]}-{i + 1:02d}"] = x
    return out


def norm(label: str) -> str:
    s = re.sub(r"[.…]+", " ", label).replace(":", " ")
    s = re.sub(r"(?<=[a-z])\d+\b", "", s.lower())   # footnote digits glued to words ("orders4")
    return re.sub(r"\s+", " ", s).strip()


def parse_advance(blob: bytes) -> tuple[list[str], dict[str, dict[str, dict[str, float]]], str | None]:
    """Advance table1a: (months newest first, {label: {"NO"/"VS": {YYYY-MM: value}}}, release date)."""
    rows = read_xlsx(blob)[0]
    months = []
    for i, r in enumerate(rows[:15]):
        cells = [str(c or "").strip() for c in r]
        if len(cells) > 4 and all(c[:3].upper() in MONTHS for c in cells[2:5]) and i + 1 < len(rows):
            years = [str(c or "").strip()[:4] for c in rows[i + 1][2:5]]
            months = [f"{y}-{MONTHS.index(c[:3].upper()) + 1:02d}" for c, y in zip(cells[2:5], years)]
            break
    if not months:
        raise SystemExit("advance table1a.xlsx: month header not found (layout changed?)")
    items: dict[str, dict[str, dict[str, float]]] = {}
    label, pending = "", False
    for r in rows:
        first = str((r[0] if r else None) or "").strip()
        if not first:
            continue
        kind = "VS" if first.startswith("Shipments") else "NO" if first.startswith("New Orders") else None
        if kind:
            vals = [num(v) for v in r[2:5]]
            if label and None not in vals:
                items.setdefault(norm(label), {})[kind] = dict(zip(months, vals))
            pending = False
            continue
        if not str(r[0]).startswith(" "):
            label, pending = "", False   # titles, section heads ("DURABLE GOODS") and footnotes are not indented
            continue
        # Item headers can wrap over two rows ("Electrical equipment, appliances," / "and components:").
        label = (label + " " + first) if pending else first
        pending = not first.endswith(":")
    text = " ".join(str(c) for r in rows for c in r if c)
    return months, items, release_date(text)


def release_date(text: str) -> str | None:
    """'..., September Advance Report, October 27, 2026.' -> 2026-10-27."""
    m = re.search(r"Report,\s*([A-Z][a-z]+\.? \d{1,2}, \d{4})", text)
    if not m:
        return None
    s = m.group(1).replace(".", "")
    for f in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def ym_prev(ym: str, n: int = 1) -> str:
    y, m = map(int, ym.split("-"))
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01", help="first month to show (YYYY-MM)")
    ap.add_argument("--out", default="durable/data/durable.json", help="output JSON path")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start + "-01")
    base = f"{start.year - 2}-12"   # 13+ months before `start` for YoY and 3m/3m changes
    rows = json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]

    hist = {}
    for suffix, kind in MEASURES.items():
        print(f"Fetching M3 history workbook ({'new orders' if suffix == 'NO' else 'shipments'})", file=sys.stderr)
        hist.update(parse_history(get(HIST_URL.format(kind=kind))))
    print("Fetching advance report table 1 and full report table 1", file=sys.stderr)
    adv_months, adv_items, adv_released = parse_advance(get(ADV_URL))
    full_released = release_date(" ".join(str(c) for r in read_xlsx(get(FULL_URL))[0] for c in r if c))

    hist_latest = max(m for k, v in hist.items() if k in ("AMDMNO", "AMDMVS") for m in v)
    use_adv = adv_months[0] > hist_latest
    missing = []
    for r in rows:
        r["levels"] = {}
        for suffix in MEASURES:
            L = {m: v for m, v in hist.get(r["m3"] + suffix, {}).items() if m >= base}
            if use_adv and r.get("adv"):
                a = adv_items.get(r["adv"], {}).get(suffix)
                if a:
                    L.update(a)
            if L:
                r["levels"][suffix] = dict(sorted(L.items()))
        if not r["levels"]:
            missing.append(r["id"])
    if use_adv:
        unmatched = sorted({r["adv"] for r in rows if r.get("adv")} - set(adv_items))
        if unmatched:
            print(f"WARNING: advance labels not found in table1a.xlsx: {unmatched}; found {sorted(adv_items)}", file=sys.stderr)
    if missing:
        print(f"WARNING: no data for: {', '.join(sorted(set(missing)))} (check m3/adv codes in series.json)", file=sys.stderr)

    latest = adv_months[0] if use_adv else hist_latest
    out = {
        "source": "U.S. Census Bureau, Manufacturers' Shipments, Inventories, and Orders (M3) survey, "
                  "seasonally adjusted, millions of dollars, not adjusted for price changes",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "report": "advance" if use_adv else "full",
        "released": adv_released if use_adv else full_released,
        "start": f"{start:%Y-%m}",
        "latest": latest,
        "latest_full": hist_latest,
        "adv_months": adv_months if use_adv else [],
        "rows": rows,
        "missing": sorted(set(missing)),
    }
    out["vintage"] = f"{latest} {out['report']}"

    # Prior vintage: keep the previous release's levels so revisions can be shown (the full report
    # revises the advance report of the same month). Re-fetching the same release keeps the older one.
    path = Path(args.out)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("vintage") != out["vintage"]:
            out["prior"] = {"vintage": old.get("vintage"), "report": old.get("report"), "latest": old.get("latest"),
                            "released": old.get("released"),
                            "levels": {r["id"]: r.get("levels", {}) for r in old["rows"] if r.get("levels")}}
        elif old.get("prior"):
            out["prior"] = old["prior"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {path} ({out['report']} report for {latest}, released {out['released']}; "
          f"full-report detail through {hist_latest})", file=sys.stderr)

    prev = ym_prev(latest)
    print(f"\n{latest} MoM % (SA)            new orders   shipments", file=sys.stderr)
    for r in rows:
        cells = []
        for s in MEASURES:
            L = r["levels"].get(s, {})
            a, b = L.get(latest), L.get(prev)
            cells.append(f"{100 * (a / b - 1):8.2f}" if a is not None and b else " " * 8)
        print(f"  {'  ' * r['level']}{r['en'][:52]:<54} {cells[0]}    {cells[1]}", file=sys.stderr)


if __name__ == "__main__":
    main()
