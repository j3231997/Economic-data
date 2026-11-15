#!/usr/bin/env python3
"""Render the GDP data JSON (from fetch_gdp.py) into a single self-contained HTML page.

Usage:
    python3 build_dashboard.py [--data gdp/data/gdp.json] [--out gdp/output/gdp_dashboard.html] [--artifact]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "template.html"
PLACEHOLDER = "/*__GDP_DATA__*/null"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="gdp/data/gdp.json")
    ap.add_argument("--out", default="gdp/output/gdp_dashboard.html")
    ap.add_argument("--artifact", action="store_true",
                    help="write a page body for Artifact publishing (no doctype/html/head/body wrapper)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    # Layout (order, level, parent, names) comes from the current series.json, so it can be edited
    # without re-fetching; numbers come from the data file.
    by_id = {r["id"]: r for r in data["rows"]}
    rows, meta = [], []
    for m in json.loads((SKILL_DIR / "series.json").read_text(encoding="utf-8"))["rows"]:
        old = by_id.get(m["id"])
        if old is None:
            print(f"WARNING: {m['id']} is in series.json but not in the data file; re-run fetch_gdp.py")
            continue
        rows.append({**old, "level": m["level"], "parent": m["parent"]})
        meta.append({"id": m["id"], "en": m["en"], "zh": m["zh"], "special": bool(m.get("special")),
                     "minus": bool(m.get("minus")), "nomCode": m["nom"], "realCode": m["real"]})
    data["rows"] = rows
    data["meta"] = meta

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
