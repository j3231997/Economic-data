#!/usr/bin/env python3
"""Render the JOLTS data JSON (from fetch_jolts.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data jolts/data/jolts.json] [--out jolts/output/jolts_dashboard.html] [--artifact]

--artifact writes the page without the doctype/html/head/body wrapper, for Artifact publishing.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "template.html"
PLACEHOLDER = "/*__JOLTS_DATA__*/null"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="jolts/data/jolts.json")
    ap.add_argument("--out", default="jolts/output/jolts_dashboard.html")
    ap.add_argument("--artifact", action="store_true",
                    help="write a page body for Artifact publishing (no doctype/html/head/body wrapper)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
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
