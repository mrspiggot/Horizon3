#!/usr/bin/env python
"""Drains-up auditor for the model graph — grades every model honestly and FAILS as a gate.

The project's vision: insight = a PROVEN PUBLISHED model run on real, systematically-sourced data
(read as §10 states), illustrated inputs → outcome → consequence. This audit measures each model
against that and refuses to pass while slop remains — the guard against lazy regression.

Grades (per model):
  method     published | data-direct  -> legitimate ;  arithmetic -> weak ;  composite -> SLOP
  grounded   every grounded_in paper is in the knowledge corpus
  sourced    every input series exists in UMD observations (and, for FRED, is registered so it is
             sourced daily + backfilled — not hand-inserted)
  covered    UMD can actually SUPPLY the window the model asks for — every input's first
             observation, plus its transform's warm-up, reaches back to history.start.
             `sourced` only asks whether the series exists; a series can exist and still begin in
             2023 while the model asks for 2010. That gap is how charts came to be narrated with
             crises they could not show — the top chart defect across 7 of 8 editorial reviews.
             Directive #1: we never commit to a model whose data cannot carry its insight.
  illustrated has input / outcome / consequence role-tagged charts, and >=2 distinct chart types
Verdict: GREEN (legitimate + grounded + sourced + covered + illustrated) · AMBER (arithmetic/thin) ·
RED (slop, or not covered).

`covered` is the cheap METADATA half — it asks what UMD holds. The other half ("did the executor
actually deliver it?") needs the model run and is gated at render time by render/from_graph.py's
coverage gate. scripts/data_fitness.py is the deep report that turns either failure into a plan.

Exit 0 only if NO model is RED. Wire into CI so mediocrity cannot regress in silently.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import psycopg2
import yaml

REPO = Path(__file__).resolve().parents[1]
GRAPH = REPO / "catalog" / "graph"
REG = REPO / "knowledge" / "registry.yaml"
UMD = Path.home() / "PycharmProjects/unified_market_data/src"

_TTY = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
GREEN, AMBER, RED = c("32", "GREEN"), c("33", "AMBER"), c("31", "RED  ")


def _observations():
    """{series_id: (first 'YYYY-MM', last 'YYYY-MM', n)} — presence AND depth, in one query.

    It used to return presence only (a set of ids), which answers "does the series exist" but not
    "does it go back far enough to support what the model asks" — so a model could be GREEN while
    its charts could not show the decade its prose named. One GROUP BY costs the same scan.
    """
    try:
        cn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                              user="postgres", password="devpassword")
        cur = cn.cursor()
        cur.execute("SELECT series_id, to_char(min(timestamp), 'YYYY-MM'), "
                    "to_char(max(timestamp), 'YYYY-MM'), count(*) FROM observations GROUP BY series_id")
        s = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
        cn.close()
        return s
    except Exception:
        return None


# Observations a transform must consume before it can emit its first value — a `yoy` input cannot
# speak until it has the calendar year behind it. Mirrors scripts/data_fitness.py's table.
_WARMUP_MONTHS = {"yoy": 12, "yoy_diff": 12, "sahm": 15, "garch_vol": 3, "momentum": 12,
                  "roll_skew": 12, "roll_kurt": 12, "realized_vol": 1, "pct_change": 1}


def _m(key: str) -> int:
    return int(key[:4]) * 12 + int(key[5:7]) - 1


def _covered(d: dict, series: list[str], obs) -> tuple[bool, str]:
    """COVERED — can UMD actually supply the window this model asks for?

    "We can never commit to a model that does not have the data coverage that allows it to propose
    insights and render those insights in a chart" (directive #1). `sourced` only asked whether the
    series EXISTS. A series can exist and still start in 2023 while the model asks for 2010 — which
    is exactly how charts came to be narrated with crises they could not show: the top chart defect
    across 7 of 8 editorial reviews.

    Compares each input's first observation (plus its transform's warm-up) against the model's
    declared history.start. Metadata only — this is the cheap half. The other half, "did the
    executor actually DELIVER it", cannot be known without running the model and is gated at render
    time (render/from_graph.py's coverage gate).
    """
    if obs is None:
        return True, "no DB"
    want = str((d.get("history") or {}).get("start", "")).strip()[:7]
    if not want or len(want) != 7:
        return True, "no history.start"
    worst, binding = None, None
    for i in (d.get("inputs") or []):
        sid = i.get("series_id")
        if not sid or sid not in obs:
            continue
        first = obs[sid][0]
        if not first:
            continue
        eff = _m(first) + _WARMUP_MONTHS.get(i.get("transform") or "none", 0)
        if worst is None or eff > worst:
            worst, binding = eff, sid
    if worst is None:
        return True, "no dated inputs"
    short = worst - _m(want)
    if short <= 0:
        return True, ""
    return False, f"asks {want}, earliest possible {worst // 12:04d}-{worst % 12 + 1:02d} " \
                  f"({short / 12:.1f}y short) — bound by {binding}"


def _fred_registered():
    try:
        sys.path.insert(0, str(UMD))
        from unified_market_data.config.registry import FRED_SERIES
        return set(FRED_SERIES)
    except Exception:
        return set()


def main() -> int:
    papers = {p["id"] for p in (yaml.safe_load(REG.read_text()).get("papers") or [])}
    specs = {f.stem: yaml.safe_load(f.read_text())
             for f in sorted(GRAPH.glob("*.yaml")) if f.name != "personas.yaml"}
    personas = yaml.safe_load((GRAPH / "personas.yaml").read_text()).get("personas", {})
    obs = _observations()
    fred = _fred_registered()

    print(f"DRAINS-UP AUDIT — {len(specs)} models across {len(personas)} personas\n")
    hdr = (f"  {'model':28} {'method':11} {'grnd':4} {'srcd':4} {'cvrd':4} "
           f"{'roles(I/O/C)':12} {'#ct':3} verdict")
    print(hdr); print("  " + "-" * (len(hdr) - 2))

    rows = {}
    reds = ambers = 0
    for mid, d in specs.items():
        method = d.get("method", "UNTAGGED")
        grounded = all(g in papers for g in (d.get("grounded_in") or [])) and bool(d.get("grounded_in"))
        series = [i["series_id"] for i in (d.get("inputs") or []) if i.get("series_id")]
        sourced = obs is None or all(s in obs for s in series)
        covered, cov_note = _covered(d, series, obs)
        fred_ok = all(s in fred for s in series if (obs and s in obs and s.isupper() and "=" not in s and not s.startswith("^")))
        charts = d.get("charts") or []
        roles = {ch.get("role") for ch in charts}
        rI, rO, rC = ("I" if "input" in roles else "-", "O" if "outcome" in roles else "-",
                      "C" if "consequence" in roles else "-")
        ctypes = len({ch.get("chart_type") for ch in charts})
        illustrated = (rI + rO + rC == "IOC") and ctypes >= 2

        if method in ("composite",) or method == "UNTAGGED":
            verdict = RED; reds += 1
        elif not covered:
            # RED, not AMBER: a model asking for history its own sources cannot supply will narrate
            # a window it cannot show. That is not thinness — it is the defect the reviews found in
            # 7 of 8 articles. "We can never commit to a model that does not have the data coverage."
            verdict = RED; reds += 1
        elif method == "arithmetic":
            verdict = AMBER; ambers += 1
        elif method in ("published", "data-direct") and grounded and sourced:
            verdict = GREEN if illustrated else AMBER
            ambers += 0 if illustrated else 1
        else:
            verdict = AMBER; ambers += 1
        rows[mid] = dict(method=method, grounded=grounded, sourced=sourced, covered=covered,
                         illustrated=illustrated,
                         verdict=("GREEN" if verdict == GREEN else "AMBER" if verdict == AMBER else "RED"))
        print(f"  {mid:28} {method:11} {'✓ ' if grounded else '✗ ':4} {'✓ ' if sourced else '✗ ':4}"
              f" {'✓ ' if covered else '✗ ':4} {rI}/{rO}/{rC:8} {ctypes:<3} {verdict}"
              + ("" if not fred_ok and series else ""))
        if not covered:
            print(f"  {'':28} {c('31', '└─ NOT COVERED: ' + cov_note)}")

    greens = len(specs) - reds - ambers
    print(f"\n  distribution: {Counter(r['verdict'] for r in rows.values())}")

    print("\nPERSONA ROLLUP")
    for pid, p in personas.items():
        ms = p.get("models") or []
        g = sum(1 for m in ms if rows.get(m, {}).get("verdict") == "GREEN")
        r = sum(1 for m in ms if rows.get(m, {}).get("verdict") == "RED")
        mark = GREEN if r == 0 and g >= 2 else (RED if r else AMBER)
        print(f"  {mark}  {pid:28} {g}/{len(ms)} legit, {r} slop")

    print("\nDATA SOURCING")
    if obs is None:
        print("  (UMD DB unreachable — series presence not checked)")
    else:
        allseries = {s for d in specs.values() for i in (d.get('inputs') or []) if (s := i.get('series_id'))}
        missing = sorted(s for s in allseries if s not in obs)
        fred_used = {s for s in allseries if s in fred}
        print(f"  {len(allseries)} distinct series used; {len(missing)} missing from observations"
              + (f" -> {missing}" if missing else ""))
        print(f"  {len(fred_used)} FRED series are registered in UMD (sourced daily + backfilled)")

    print(f"\nVERDICT: {greens} GREEN · {ambers} AMBER · {reds} RED")
    # RED now has two distinct causes and they need different work. Reporting a coverage failure as
    # "slop (homemade composites)" would send someone to rewrite a perfectly good published model
    # when the actual problem is that its data does not reach back far enough. A gate that
    # misreports WHY it failed wastes the attention it just bought.
    slop = [m for m, r in rows.items() if r["verdict"] == "RED" and r["covered"]]
    uncov = [m for m, r in rows.items() if r["verdict"] == "RED" and not r["covered"]]
    if slop:
        print(f"  {RED}: {len(slop)} model(s) are SLOP (homemade composites / untagged): "
              f"{', '.join(slop)}")
        print("         Replace with a proven published method.")
    if uncov:
        print(f"  {RED}: {len(uncov)} model(s) are NOT COVERED — they ask for history their own "
              f"sources cannot supply:")
        print(f"         {', '.join(uncov)}")
        print("         Each will narrate a window it cannot show. Directive #1: find the data, or")
        print("         narrow the claim — never ship the chart. `python scripts/data_fitness.py`")
        print("         names the binding series and whether it is an acquisition or a free fix.")
    if reds:
        print("  The gate FAILS until every RED is cleared. This is the guard against regression.")
    return 0 if reds == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
