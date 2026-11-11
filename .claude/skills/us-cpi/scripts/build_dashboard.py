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


def ym_prev(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def relative_importance(code: str, month: str, rows: dict, weights: dict) -> float | None:
    """Relative importance of `code` in `month`, carried from the nearest snapshot by relative price change.

    RI_m = RI_a * (I_m / I_a) / (AllItems_m / AllItems_a), NSA indexes. Snapshots are the latest Table 2
    weights (as_of) plus weights.json "anchors" (e.g. BLS December tables). The first snapshot on or after
    `month` is preferred (stays within one weight vintage), else the latest one before it.
    """
    snaps = {weights["as_of"]: weights["weights"], **weights.get("anchors", {})}
    snaps = {a: v for a, v in snaps.items() if code in v}
    if not snaps:
        return None
    after = sorted(a for a in snaps if a >= month)
    a = after[0] if after else max(snaps)
    idx, allx = rows[code]["nsa"], rows["SA0"]["nsa"]
    if not all(k in d for d in (idx, allx) for k in (month, a)):
        return None
    return snaps[a][code] * (idx[month] / idx[a]) / (allx[month] / allx[a])


def derived_terms(d: dict) -> list[tuple[str, int]]:
    """[(code, +1/-1), ...] for a derived spec {"plus": [...], "minus": [...]} ("base" = one plus item)."""
    plus = d.get("plus") or [d["base"]]
    return [(c, 1) for c in plus] + [(c, -1) for c in d.get("minus", [])]


def derived_formula(d: dict) -> str:
    return " ".join(("+ " if s > 0 else "− ") + c for c, s in derived_terms(d))[2:]


def compute_derived(row: dict, rows: dict, weights: dict) -> None:
    """Build a derived aggregate (sum of plus items minus minus items) as a chained index.

    change_t = sum(s_i * w_i * g_i) / sum(s_i * w_i), s_i = +1/-1, w = previous-month relative importance,
    g = unrounded % change of the SA (for "sa") or NSA (for "nsa") index. When the previous month is
    missing (e.g. 2025-10), the change is taken from the last available month.
    """
    terms = derived_terms(row["derived"])
    for key in ("sa", "nsa"):
        series = [rows[c][key] for c, _ in terms]
        months = sorted(set.intersection(*(set(x) for x in series)))
        level, prev = {}, None
        for m in months:
            if prev is None:
                level[m] = 100.0
                prev = m
                continue
            w = [relative_importance(c, prev, rows, weights) for c, _ in terms]
            if None in w:
                prev = None
                continue
            num = sum(s * wi * (x[m] / x[prev] - 1) for (_, s), wi, x in zip(terms, w, series))
            den = sum(s * wi for (_, s), wi in zip(terms, w))
            level[m] = level[prev] * (1 + num / den)
            prev = m
        row[key] = level


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
        if "derived" in meta:
            rows.append({**meta, "sa": {}, "nsa": {}})
            continue
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
            if r["weight"] is None and "derived" not in r:
                missing.append(r["code"])
        if missing:
            print(f"WARNING: no weight in weights.json for: {', '.join(missing)}")
        for r in data["rows"]:
            if "derived" in r:
                compute_derived(r, {x["code"]: x for x in data["rows"]}, w)
                r["weight"] = round(sum(s * w["weights"][c] for c, s in derived_terms(r["derived"])), 3)
                r["formula"] = derived_formula(r["derived"])
    data["rows"] = [r for r in data["rows"] if not r.get("hidden")]  # hidden = fetched only as an input
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
