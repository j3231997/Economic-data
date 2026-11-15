#!/usr/bin/env python3
"""Build the macro-data hub page: one card per dashboard with its link, latest month,
headline figures and a 12-month mini chart, read from each dashboard's data JSON.

Usage (from the repo root):
    python3 .claude/skills/macro-hub/scripts/build_hub.py [--out hub/macro_hub.html]

The output is a page body for Artifact publishing (no doctype/html/head/body wrapper);
it also opens fine as a local file in a browser.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ROOT = SKILL_DIR.parent.parent.parent


def ym_prev(ym: str, n: int = 1) -> str:
    y, m = map(int, ym.split("-"))
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def pct(a, b):
    return None if a is None or b is None or not b else (a / b - 1) * 100


def months_back(latest: str, n: int) -> list[str]:
    return [ym_prev(latest, i) for i in range(n - 1, -1, -1)]


def nfp(d: dict) -> dict:
    L = d["rows"][0]["levels"]
    latest = max(L)
    ch = lambda m: L[m] - L[ym_prev(m)] if m in L and ym_prev(m) in L else None
    avg3 = (L[latest] - L[ym_prev(latest, 3)]) / 3
    return {
        "latest": latest, "prelim": latest in d["rows"][0].get("prelim", []), "fetched": d["fetched_at"],
        "figures": [
            {"k": "非農就業 MoM", "v": ch(latest), "fmt": "k0", "sign": True},
            {"k": "3 個月平均", "v": avg3, "fmt": "k0", "sign": True},
            {"k": "就業人數", "v": L[latest] / 1000, "unit": "M", "fmt": "f1"},
        ],
        "chart": {"label": "非農 MoM（千人）", "type": "bar", "ref": 0,
                  "points": [[m, ch(m)] for m in months_back(latest, 12)]},
    }


def wages(d: dict) -> dict:
    L = d["rows"][0]["levels"]
    latest = max(L)
    mom = lambda m: pct(L.get(m), L.get(ym_prev(m)))
    return {
        "latest": latest, "prelim": latest in d["rows"][0].get("prelim", []), "fetched": d["fetched_at"],
        "figures": [
            {"k": "時薪 MoM", "v": mom(latest), "unit": "%", "fmt": "f2", "note": f"官方 {round(mom(latest) + 1e-9, 1):.1f}%"},
            {"k": "YoY", "v": pct(L[latest], L.get(ym_prev(latest, 12))), "unit": "%", "fmt": "f1"},
            {"k": "民間平均時薪", "v": L[latest], "unit": "$", "fmt": "f2", "prefix": True},
        ],
        "chart": {"label": "時薪 MoM %（虛線 0.30%）", "type": "bar", "ref": 0.3,
                  "points": [[m, mom(m)] for m in months_back(latest, 12)]},
    }


def jolts(d: dict) -> dict:
    t = d["rows"][0]["data"]
    J, R, Q = t["JO"]["level"], t["JO"]["rate"], t["QU"]["rate"]
    latest = max(J)
    u = d.get("unemployed", {}).get(latest)
    return {
        "latest": latest, "prelim": latest in d.get("prelim", []), "fetched": d["fetched_at"],
        "figures": [
            {"k": "職缺", "v": J[latest] / 1000, "unit": "M", "fmt": "f2",
             "note": f"MoM {J[latest] - J[ym_prev(latest)]:+,.0f}k"},
            {"k": "職缺率", "v": R[latest], "unit": "%", "fmt": "f1", "note": f"自願離職率 {Q[latest]:.1f}%"},
            {"k": "失業人數 ÷ 職缺", "v": u / J[latest] if u else None, "fmt": "f2"},
        ],
        "chart": {"label": "職缺（百萬）", "type": "line",
                  "points": [[m, J[m] / 1000 if m in J else None] for m in months_back(latest, 12)]},
    }


def cpi(d: dict) -> dict:
    rows = {r["code"]: r for r in d["rows"]}
    head, core = rows["SA0"], rows["SA0L1E"]
    latest = max(head["sa"])
    mom = lambda r, m: pct(r["sa"].get(m), r["sa"].get(ym_prev(m)))
    yoy = lambda r, m: pct(r["nsa"].get(m), r["nsa"].get(ym_prev(m, 12)))
    hm, cm = mom(head, latest), mom(core, latest)
    yn = lambda r: f"YoY {yoy(r, latest):.1f}%" if yoy(r, latest) is not None else "YoY 無資料（2025/10 未公布）"
    return {
        "latest": latest, "prelim": False, "fetched": d["fetched_at"],
        "figures": [
            {"k": "CPI MoM", "v": hm, "unit": "%", "fmt": "f2", "note": yn(head)},
            {"k": "核心 MoM", "v": cm, "unit": "%", "fmt": "f2", "note": yn(core)},
        ],
        "chart": {"label": "核心 CPI MoM %（虛線 0.20%）", "type": "bar", "ref": 0.2,
                  "points": [[m, mom(core, m)] for m in months_back(latest, 12)]},
    }


KINDS = {"nfp": nfp, "wages": wages, "jolts": jolts, "cpi": cpi}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="hub/macro_hub.html")
    args = ap.parse_args()

    cfg = json.loads((SKILL_DIR / "pages.json").read_text(encoding="utf-8"))
    cards = []
    for p in cfg["pages"]:
        path = ROOT / p["data"]
        card = {k: p[k] for k in ("group", "title", "url", "release", "desc", "skill")}
        if path.exists():
            card.update(KINDS[p["kind"]](json.loads(path.read_text(encoding="utf-8"))))
        else:
            print(f"WARNING: {path} not found; card shows the link only")
        cards.append(card)
    payload = json.dumps({"groups": cfg["groups"], "cards": cards}, ensure_ascii=False, separators=(",", ":"))
    html = (SKILL_DIR / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__HUB_DATA__*/null", payload.replace("</", "<\\/"))
    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    for c in cards:
        print(f"  {c['title']:<16} {c.get('latest', 'n/a')}")


if __name__ == "__main__":
    main()
