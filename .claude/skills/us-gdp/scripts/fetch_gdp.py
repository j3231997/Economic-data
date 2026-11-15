#!/usr/bin/env python3
"""Fetch US GDP by expenditure component (BEA NIPA) and the Atlanta Fed GDPNow nowcast.

Reads the component hierarchy from ../series.json and downloads:
  * BEA NIPA quarterly flat file https://apps.bea.gov/national/Release/TXT/NipaDataQ.txt (~35 MB, every
    published quarterly NIPA series, no API key). Its Last-Modified header is taken as the release date.
  * GDPNow workbook https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/gdpnow/GDPTrackingModelDataAndForecasts.xlsx
    (sheets ContribHistory / TrackingHistory: every nowcast update for the quarter being tracked, with
    13 subcomponents' growth and contributions; TableCont: the data release behind each update).

Real contributions: rows with an official BEA contribution series (`ry`, Table 1.1.2) use it. Other rows
use BEA's exact Fisher decomposition (NIPA Handbook ch. 4):
    C_i = 100 * (p_i,t / P_t + p_i,t-1) * (q_i,t - q_i,t-1) / sum_j (p_j,t / P_t + p_j,t-1) * q_j,t-1
annualized with ((1+g)^4 - 1) / g, then reconciled so children add up to the parent's published value
(BEA applies unpublished quarterly adjustments, so the raw formula can be a few bp off).

If --out already exists and holds a different vintage (GDP levels changed), its data is kept as the
"prior vintage" so the dashboard can show revisions.

Usage:
    python3 fetch_gdp.py [--start 2022Q1] [--out gdp/data/gdp.json] [--estimate A|S|T] [--no-gdpnow]

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import email.utils
import hashlib
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
BEA_URL = "https://apps.bea.gov/national/Release/TXT/NipaDataQ.txt"
GDPNOW_URL = ("https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/"
              "data/gdpnow/GDPTrackingModelDataAndForecasts.xlsx")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
EST_NAMES = {"A": "advance", "S": "second", "T": "third"}


def get(url: str, retries: int = 3) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (economic-data fetcher)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read(), dict(r.headers)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise SystemExit(f"download failed: {url}: {e}")
            wait = 2 ** (attempt + 1)
            print(f"  network error ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def qprev(q: str, n: int = 1) -> str:
    y, k = int(q[:4]), int(q[5])
    k -= n
    while k <= 0:
        k += 4
        y -= 1
    return f"{y}Q{k}"


def qend(q: str) -> dt.date:
    y, k = int(q[:4]), int(q[5])
    return dt.date(y, 3 * k, 30 if k in (2, 3) else 31)


# --- BEA ---------------------------------------------------------------------------------------

def load_bea(codes: set[str], first: str) -> tuple[dict[str, dict[str, float]], str | None]:
    print(f"Downloading {BEA_URL} ...")
    blob, headers = get(BEA_URL)
    released = None
    if headers.get("Last-Modified"):
        released = email.utils.parsedate_to_datetime(headers["Last-Modified"]).date().isoformat()
    out: dict[str, dict[str, float]] = {c: {} for c in codes}
    rd = csv.reader(io.StringIO(blob.decode("utf-8-sig")))
    next(rd)
    for code, per, val in rd:
        if code in out and per >= first:
            try:
                out[code][per] = float(val.replace(",", ""))
            except ValueError:
                pass
    return out, released


def real_contributions(rows: list[dict], quarters: list[str]) -> dict[str, dict[str, float]]:
    """Exact Fisher contributions to real GDP growth (annualized, pp) for every row, before reconciliation."""
    by = {r["id"]: r for r in rows}
    top = [r for r in rows if r["parent"] == "GDP" and not r.get("special")]
    out: dict[str, dict[str, float]] = {r["id"]: {} for r in rows}
    gdp = by["GDP"]
    for q in quarters:
        p = qprev(q)
        try:
            Qf = gdp["R"][q] / gdp["R"][p]
            Pf = (gdp["N"][q] / gdp["N"][p]) / Qf
        except (KeyError, ZeroDivisionError):
            continue
        g = Qf - 1
        ann = (Qf ** 4 - 1) / g if abs(g) > 1e-12 else 4.0

        def term(r):
            n0, n1, x0, x1 = r["N"].get(p), r["N"].get(q), r["R"].get(p), r["R"].get(q)
            if None in (n0, n1, x0, x1) or not x0 or not x1:
                return None
            sg = -1 if r.get("minus") else 1
            if r["id"] in ("CIPI", "NX"):   # level can cross zero: no meaningful implicit price
                return None
            w = n1 / x1 / Pf + n0 / x0
            return sg * w * (x1 - x0), sg * w * x0

        # Denominator over GDP's final-demand partition; inventories enter with a constant-price weight.
        parts = []
        for r in top:
            if r["id"] == "GPDI":
                parts += [by["FI"], by["CIPI"]]
            elif r["id"] == "NX":
                parts += [by["EX"], by["IM"]]
            else:
                parts.append(r)
        D = 0.0
        for r in parts:
            if r["id"] == "CIPI":
                D += r["N"].get(p, 0.0) * (1 + 1 / Pf)
            else:
                t = term(r)
                if t is None:
                    D = None
                    break
                D += t[1]
        if not D:
            continue
        for r in rows:
            t = term(r)
            if t is not None:
                out[r["id"]][q] = t[0] / D * 100 * ann
    return out


def reconcile(rows: list[dict], calc: dict[str, dict[str, float]], quarters: list[str]) -> tuple[dict, dict]:
    """Official contribution where published; otherwise computed and adjusted so children sum to the parent."""
    by = {r["id"]: r for r in rows}
    kids = {r["id"]: [c for c in rows if c["parent"] == r["id"] and not c.get("special")] for r in rows}
    final: dict[str, dict[str, float]] = {r["id"]: {} for r in rows}
    src: dict[str, str] = {}
    for r in rows:
        if r.get("ry"):
            final[r["id"]] = dict(r["RY"])
            src[r["id"]] = "bea"
    # CIPI / NX residuals only when not published (they always are), GDP total = growth.
    for q in quarters:
        g = by["GDP"]["R"]
        if q in g and qprev(q) in g:
            final["GDP"][q] = ((g[q] / g[qprev(q)]) ** 4 - 1) * 100
    src["GDP"] = "bea"

    def walk(pid: str):
        ch = kids[pid]
        free = [c for c in ch if not c.get("ry")]
        if free:
            for q in quarters:
                if q not in final[pid]:
                    continue
                fixed = sum(final[c["id"]].get(q, 0.0) for c in ch if c.get("ry"))
                vals = {c["id"]: calc[c["id"]].get(q) for c in free}
                if any(v is None for v in vals.values()):
                    continue
                gap = final[pid][q] - fixed - sum(vals.values())
                w = {c["id"]: abs(c["N"].get(qprev(q), 0.0)) for c in free}
                tw = sum(w.values()) or 1.0
                for cid, v in vals.items():
                    final[cid][q] = v + gap * w[cid] / tw
            for c in free:
                src[c["id"]] = "calc"
        for c in ch:
            walk(c["id"])

    walk("GDP")
    for r in rows:
        if r.get("sum"):
            final[r["id"]] = {q: sum(final[s].get(q, 0.0) for s in r["sum"]) for q in quarters
                              if all(q in final[s] for s in r["sum"])}
            src[r["id"]] = "bea"
    return final, src


# --- GDPNow ------------------------------------------------------------------------------------

def read_sheets(blob: bytes, names: set[str]) -> dict[str, list[list]]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        if sh.get("name") not in names:
            continue
        target = rels[sh.get(f"{{{NS['r']}}}id")].lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(path)).iter(f"{{{NS['m']}}}row"):
            vals: list = []
            for c in row.findall("m:c", NS):
                i = 0
                for ch in re.match(r"[A-Z]+", c.get("r")).group(0):
                    i = i * 26 + ord(ch) - 64
                i -= 1
                vals.extend([None] * (i - len(vals) + 1))
                v = c.find("m:v", NS)
                if c.get("t") == "s" and v is not None:
                    vals[i] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    vals[i] = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None:
                    vals[i] = v.text
            rows.append(vals)
        out[sh.get("name")] = rows
    return out


def xl_date(v) -> str:
    return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(v)))).isoformat()


def load_gdpnow(rows: list[dict]) -> dict | None:
    print(f"Downloading GDPNow workbook ...")
    try:
        blob, _ = get(GDPNOW_URL)
        sh = read_sheets(blob, {"ContribHistory", "TrackingHistory", "TableCont"})
    except (SystemExit, zipfile.BadZipFile, KeyError) as e:
        print(f"WARNING: GDPNow not loaded: {e}", file=sys.stderr)
        return None
    keys = {r["gdpnow"]: r["id"] for r in rows if r.get("gdpnow")}

    def parse(sheet):
        tab = sh[sheet]
        dates = [xl_date(v) for v in tab[0][2:] if v]
        title = next((r[0] for r in tab if r and r[0] and "nowcast" in str(r[0]).lower()), "")
        m = re.search(r"(\d{4})q(\d)", str(title), re.I)
        quarter = f"{m.group(1)}Q{m.group(2)}" if m else None
        vals: dict[str, list] = {}
        for r in tab:
            if len(r) < 3 or not r[1]:
                continue
            lab = str(r[1]).strip()
            m2 = re.match(r"(\d+)-", lab)
            if m2:
                k = m2.group(1)
            elif lab.isdigit():
                continue   # e.g. the "Number of Dates in Spreadsheet" count
            else:
                k = lab.replace(" ($Bil 2017)", "").rstrip("*").strip()
            if k in keys:
                vals[keys[k]] = [float(x) if x not in (None, "") else None for x in r[2:2 + len(dates)]]
        return quarter, dates, vals

    q1, dates, contrib = parse("ContribHistory")
    q2, dates2, growth = parse("TrackingHistory")
    for k in ("NX", "CIPI"):   # TrackingHistory holds $bn changes for these, not growth rates
        growth.pop(k, None)
    for r in rows:   # aggregates GDPNow reports only as growth (final sales to private domestic purchasers)
        if r.get("sum") and r["id"] not in contrib and all(s in contrib for s in r["sum"]):
            contrib[r["id"]] = [sum(contrib[s][i] or 0 for s in r["sum"]) for i in range(len(dates))]
    releases = {}
    for r in sh.get("TableCont", []):
        if r and r[0] and re.fullmatch(r"\d+(\.0+)?", str(r[0])) and len(r) > 1 and r[1]:
            releases[xl_date(r[0])] = str(r[1])
    missing = sorted(set(keys.values()) - set(contrib) - set(growth))
    if missing:
        print(f"WARNING: GDPNow rows not found: {missing} (check `gdpnow` keys in series.json)", file=sys.stderr)
    return {"quarter": q1, "dates": dates, "releases": [releases.get(d, "") for d in dates],
            "contrib": contrib, "growth": growth}


# --- main --------------------------------------------------------------------------------------

def estimate_flag(latest: str, released: str | None) -> str:
    if not released:
        return "A"
    days = (dt.date.fromisoformat(released) - qend(latest)).days
    return "A" if days <= 45 else "S" if days <= 75 else "T"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2022Q1", help="first quarter shown (YoY needs 4 more, fetched automatically)")
    ap.add_argument("--out", default="gdp/data/gdp.json")
    ap.add_argument("--estimate", choices=list(EST_NAMES), help="override the inferred A/S/T estimate of the latest quarter")
    ap.add_argument("--no-gdpnow", action="store_true")
    args = ap.parse_args()

    meta = json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]
    first = qprev(args.start, 5)
    codes = {r[k] for r in meta for k in ("nom", "real", "pct", "ry") if r.get(k)}
    data, released = load_bea(codes, first)
    missing = sorted(c for c in codes if not data[c])
    if missing:
        print(f"WARNING: no data for {missing}", file=sys.stderr)

    rows = []
    for r in meta:
        rows.append({**r, "N": data.get(r["nom"], {}), "R": data.get(r["real"], {}),
                     "PCT": data.get(r.get("pct"), {}) if r.get("pct") else {},
                     "RY": data.get(r.get("ry"), {}) if r.get("ry") else {}})
    quarters = sorted(rows[0]["N"])
    latest = quarters[-1]
    calc = real_contributions(rows, quarters[1:])
    contrib, src = reconcile(rows, calc, quarters[1:])

    # Check: raw formula vs official, for the log.
    recent = quarters[-8:]
    worst = max(((abs(calc[r["id"]][q] - r["RY"][q]), r["id"], q) for r in rows if r.get("ry")
                 for q in recent if q in calc[r["id"]] and q in r["RY"]), default=(0, "", ""))
    print(f"Exact-formula contributions vs BEA Table 1.1.2, last 8 quarters: max gap {worst[0]:.3f} pp "
          f"({worst[1]} {worst[2]}); detail rows are reconciled to the published parents")

    vintage_src = json.dumps([rows[0]["N"].get(q) for q in quarters[-6:]] + [rows[0]["R"].get(q) for q in quarters[-6:]])
    vintage = latest + ":" + hashlib.sha1(vintage_src.encode()).hexdigest()[:10]
    out_rows = []
    for r in rows:
        o = {k: r[k] for k in ("id", "level", "parent")}
        o["nom"] = r["N"]
        o["real"] = r["R"]
        if r["PCT"]:
            o["pct"] = r["PCT"]
        o["contrib"] = {q: round(v, 6) for q, v in contrib.get(r["id"], {}).items()}
        o["csrc"] = src.get(r["id"], "calc")
        out_rows.append(o)

    est = args.estimate or estimate_flag(latest, released)
    result = {
        "source": "BEA NIPA（NipaDataQ.txt）＋ Atlanta Fed GDPNow",
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "released": released, "latest": latest, "estimate": est, "start": args.start,
        "vintage": vintage, "rows": out_rows,
    }
    if not args.no_gdpnow:
        gn = load_gdpnow(meta)
        if gn and gn["quarter"] and gn["quarter"] > latest:
            result["gdpnow"] = gn
        elif gn:
            print(f"GDPNow tracks {gn['quarter']}, not after the latest BEA quarter {latest}: not shown")

    out = Path(args.out)
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
        if old.get("vintage") and old["vintage"] != vintage:
            result["prior"] = {"vintage": old["vintage"], "latest": old.get("latest"), "released": old.get("released"),
                               "estimate": old.get("estimate"),
                               "rows": {r["id"]: {k: r.get(k, {}) for k in ("nom", "real", "contrib")} for r in old["rows"]}}
            print(f"Prior vintage kept: {old.get('latest')} {old.get('estimate')} ({old.get('released')})")
        elif old.get("prior"):
            result["prior"] = old["prior"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {out}: {quarters[0]}–{latest} ({EST_NAMES[est]} estimate, file dated {released})")

    # Summary for quoting.
    by = {r["id"]: r for r in out_rows}
    p = qprev(latest)
    print(f"\n{latest} real GDP {((by['GDP']['real'][latest] / by['GDP']['real'][p]) ** 4 - 1) * 100:.2f}% SAAR "
          f"(official {by['GDP'].get('pct', {}).get(latest)}); contributions pp:")
    for k in ("PCE", "GPDI", "FI", "CIPI", "NX", "GOV", "PDFP"):
        print(f"  {k:5s} {by[k]['contrib'].get(latest, float('nan')):6.2f}")
    if result.get("gdpnow"):
        gn = result["gdpnow"]
        print(f"GDPNow {gn['quarter']} ({gn['dates'][-1]}): {gn['contrib']['GDP'][-1]:.2f}%")


if __name__ == "__main__":
    main()
