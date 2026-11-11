#!/usr/bin/env python3
"""Render the CPI data JSON (from fetch_cpi.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data data/cpi.json] [--out output/cpi_dashboard.html]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "template.html"
WEIGHTS = SKILL_DIR / "weights.json"
PLACEHOLDER = "/*__CPI_DATA__*/null"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/cpi.json")
    ap.add_argument("--out", default="output/cpi_dashboard.html")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    # Layout (order, level, parent, names, pinning) comes from the current series.json, so it can be
    # edited without re-fetching; index values come from the data file.
    by_code = {r["code"]: r for r in data["rows"]}
    rows = []
    for meta in json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]:
        old = by_code.get(meta["code"])
        if old is None:
            print(f"WARNING: {meta['code']} is in series.json but not in the data file; re-run fetch_cpi.py")
            continue
        rows.append({**meta, "sa": old.get("sa", {}), "nsa": old.get("nsa", {})})
    data["rows"] = rows
    # Relative importance lives in weights.json so it can be refreshed without re-fetching the indexes.
    if WEIGHTS.exists():
        w = json.loads(WEIGHTS.read_text(encoding="utf-8"))
        data["weights_as_of"] = w.get("as_of")
        missing = []
        for r in data["rows"]:
            r["weight"] = w["weights"].get(r["code"])
            if r["weight"] is None:
                missing.append(r["code"])
        if missing:
            print(f"WARNING: no weight in weights.json for: {', '.join(missing)}")
    html = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        raise SystemExit("template.html is missing the data placeholder")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html.replace(PLACEHOLDER, payload), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
