#!/usr/bin/env python3
"""Render the durable goods data JSON (from fetch_durable.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data durable/data/durable.json] [--out durable/output/durable_dashboard.html] [--artifact]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "template.html"
PLACEHOLDER = "/*__DURABLE_DATA__*/null"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="durable/data/durable.json")
    ap.add_argument("--out", default="durable/output/durable_dashboard.html")
    ap.add_argument("--artifact", action="store_true",
                    help="write a page body for Artifact publishing (no doctype/html/head/body wrapper)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    # Layout (order, level, parent, names) comes from the current series.json, so it can be edited
    # without re-fetching; levels come from the data file.
    by_id = {r["id"]: r for r in data["rows"]}
    rows = []
    for meta in json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]:
        old = by_id.get(meta["id"])
        if old is None:
            print(f"WARNING: {meta['id']} is in series.json but not in the data file; re-run fetch_durable.py")
            continue
        rows.append({**meta, "levels": old.get("levels", {})})
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
