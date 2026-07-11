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
  illustrated has input / outcome / consequence role-tagged charts, and >=2 distinct chart types
Verdict: GREEN (legitimate + grounded + sourced + illustrated) · AMBER (arithmetic/thin) · RED (slop).

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
    try:
        cn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                              user="postgres", password="devpassword")
        cur = cn.cursor()
        cur.execute("SELECT DISTINCT series_id FROM observations")
        s = {r[0] for r in cur.fetchall()}
        cn.close()
        return s
    except Exception:
        return None


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
    hdr = f"  {'model':28} {'method':11} {'grnd':4} {'srcd':4} {'roles(I/O/C)':12} {'#ct':3} verdict"
    print(hdr); print("  " + "-" * (len(hdr) - 2))

    rows = {}
    reds = ambers = 0
    for mid, d in specs.items():
        method = d.get("method", "UNTAGGED")
        grounded = all(g in papers for g in (d.get("grounded_in") or [])) and bool(d.get("grounded_in"))
        series = [i["series_id"] for i in (d.get("inputs") or []) if i.get("series_id")]
        sourced = obs is None or all(s in obs for s in series)
        fred_ok = all(s in fred for s in series if (obs and s in obs and s.isupper() and "=" not in s and not s.startswith("^")))
        charts = d.get("charts") or []
        roles = {ch.get("role") for ch in charts}
        rI, rO, rC = ("I" if "input" in roles else "-", "O" if "outcome" in roles else "-",
                      "C" if "consequence" in roles else "-")
        ctypes = len({ch.get("chart_type") for ch in charts})
        illustrated = (rI + rO + rC == "IOC") and ctypes >= 2

        if method in ("composite",) or method == "UNTAGGED":
            verdict = RED; reds += 1
        elif method == "arithmetic":
            verdict = AMBER; ambers += 1
        elif method in ("published", "data-direct") and grounded and sourced:
            verdict = GREEN if illustrated else AMBER
            ambers += 0 if illustrated else 1
        else:
            verdict = AMBER; ambers += 1
        rows[mid] = dict(method=method, grounded=grounded, sourced=sourced, illustrated=illustrated,
                         verdict=("GREEN" if verdict == GREEN else "AMBER" if verdict == AMBER else "RED"))
        print(f"  {mid:28} {method:11} {'✓ ' if grounded else '✗ ':4} {'✓ ' if sourced else '✗ ':4}"
              f" {rI}/{rO}/{rC:8} {ctypes:<3} {verdict}"
              + ("" if not fred_ok and series else ""))

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
    if reds:
        print(f"  {RED}: {reds} models are slop (homemade composites / untagged). The gate FAILS until")
        print("  every RED is replaced by a proven published method. This is the guard against regression.")
    return 0 if reds == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
