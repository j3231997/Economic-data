#!/usr/bin/env python3
"""Render the CPI data JSON (from fetch_cpi.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data data/cpi.json] [--out output/cpi_dashboard.html]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"
PLACEHOLDER = "/*__CPI_DATA__*/null"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/cpi.json")
    ap.add_argument("--out", default="output/cpi_dashboard.html")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
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
