#!/usr/bin/env python3
"""Render the retail sales data JSON (from fetch_retail.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data retail/data/retail.json] [--out retail/output/retail_dashboard.html] [--artifact]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "template.html"
PLACEHOLDER = "/*__RETAIL_DATA__*/null"


def derived_terms(d: dict) -> list[tuple[str, int]]:
    """[(id, +1/-1), ...] for {"plus": [...], "minus": [...]} ("base" = a single plus item)."""
    plus = d.get("plus") or [d["base"]]
    return [(c, 1) for c in plus] + [(c, -1) for c in d.get("minus", [])]


def combine(levels: list[dict], signs: list[int]) -> dict:
    """Dollar levels are additive: sum of signed levels over the months every input has."""
    months = sorted(set.intersection(*(set(L) for L in levels))) if levels else []
    return {m: round(sum(s * L[m] for L, s in zip(levels, signs)), 1) for m in months}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="retail/data/retail.json")
    ap.add_argument("--out", default="retail/output/retail_dashboard.html")
    ap.add_argument("--artifact", action="store_true",
                    help="write a page body for Artifact publishing (no doctype/html/head/body wrapper)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    # Layout (order, level, parent, names, derived formulas) comes from the current series.json, so it
    # can be edited without re-fetching; levels come from the data file.
    by_id = {r["id"]: r for r in data["rows"]}
    rows = []
    for meta in json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]:
        if "derived" in meta:
            rows.append({**meta, "levels": {}})
            continue
        old = by_id.get(meta["id"])
        if old is None:
            print(f"WARNING: {meta['id']} is in series.json but not in the data file; re-run fetch_retail.py")
            continue
        rows.append({**meta, "levels": old.get("levels", {})})
    by_id = {r["id"]: r for r in rows}
    prior = data.get("prior", {}).get("levels", {})
    for r in rows:
        if "derived" not in r:
            continue
        terms = derived_terms(r["derived"])
        if any(c not in by_id for c, _ in terms):
            print(f"WARNING: {r['id']}: derived input missing; skipped")
            continue
        r["levels"] = combine([by_id[c]["levels"] for c, _ in terms], [s for _, s in terms])
        r["formula"] = " ".join(("+ " if s > 0 else "− ") + c for c, s in terms)[2:]
        if prior and all(c in prior for c, _ in terms):
            prior[r["id"]] = combine([prior[c] for c, _ in terms], [s for _, s in terms])
    data["rows"] = rows

    html = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        raise SystemExit("template.html is missing the data placeholder")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace(PLACEHOLDER, payload)
    if args.artifact:
        # The Artifact host adds its own doctype/head/body skeleton: keep <title>, <style> and the body content.
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        head = "\n".join(re.findall(r"<title>.*?</title>|<style>.*?</style>", head, re.S))
        body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
        html = head + "\n" + body
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
