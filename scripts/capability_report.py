"""CAPABILITY REPORT — for every persona and every model: what charts render, and what insights fire?

The question this answers is the one that decides whether any of the render work generalises:
across ALL 8 personas and ALL 28 models, does every authored chart actually draw, through the
polished family or the raw fallback — and which of the 46 authored interpretations are TRUE on
today's data?

Why this exists: every verification so far has been on central_bank_policymaker. That is precisely
the failure the charter names — "Generic, not FOMC. Prove things across the full decision-maker
matrix. FOMC is one row, never the yardstick — the recurring Horizon2 failure." A fix proven on one
persona is not a fix; it is an anecdote.

Two axes, because "what can we say" has two halves:

  CHARTS   per chart: family (the polished studio renderer) / raw (the charts.py fallback, whose
           defaults were never meant to ship) / REFUSED (the coverage gate) / FAIL. A chart that
           silently falls back is the `two-visual-systems` defect (8/8 reviews) still live.

  INSIGHTS per model: the authored `interpretations` are `when:` guards over executed outputs
           (writer._active_says evals them against latest.outputs). An interpretation that FIRES is
           a claim the app is entitled to make about this market today. One that never fires for any
           persona is a claim we have never been able to make — dead weight in the catalog, and
           invisible until you look.

    ~/venv/bin/python scripts/capability_report.py
    ~/venv/bin/python scripts/capability_report.py --persona credit_investor
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402
import yaml      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.graph_corpus import GRAPH_DIR, run_model  # noqa: E402
from render.infographic.from_persona import chart_png, chart_png_family  # noqa: E402
from render.writer import _active_says  # noqa: E402

RED, AMBER, GREEN, BOLD, DIM, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[1m", "\033[2m", "\033[0m"


def chart_status(run: dict, cid: str) -> str:
    """family | raw | REFUSED | FAIL — how (and whether) this chart actually draws."""
    try:
        if chart_png_family(run, cid)[0]:
            return "family"
    except Exception:
        pass
    try:
        return "raw" if chart_png(run, cid) else "FAIL"
    except ValueError as exc:
        return "REFUSED" if "DATA STARVED" in str(exc) else "FAIL"
    except Exception:
        return "FAIL"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", help="just one persona")
    args = ap.parse_args()

    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]
    if args.persona:
        personas = {args.persona: personas[args.persona]}

    tally = collections.Counter()
    fired_total = declared_total = 0
    dead_interps: list[str] = []
    model_rows: list[tuple] = []

    for pid, p in personas.items():
        print(f"\n{BOLD}{pid}{OFF}  ({len(p.get('models') or [])} models)")
        for mid in (p.get("models") or []):
            try:
                run = run_model(mid, conn)
            except Exception as exc:
                print(f"  {RED}{mid:28} MODEL FAILED: {type(exc).__name__}: {str(exc)[:44]}{OFF}")
                tally["model_fail"] += 1
                continue
            cov = run.get("coverage") or {}
            charts = [c.get("id") for c in (run.get("charts") or []) if c.get("id")]
            st = collections.Counter(chart_status(run, cid) for cid in charts)
            for k, v in st.items():
                tally[k] += v

            says = _active_says(run.get("meta") or {}, run.get("latest"))
            interps = (run.get("meta") or {}).get("interpretations") or []
            declared_total += len(interps)
            fired_total += len(says)
            if interps and not says:
                dead_interps.append(f"{pid}/{mid}")

            bad = st.get("raw", 0) + st.get("FAIL", 0) + st.get("REFUSED", 0)
            col = GREEN if not bad else (AMBER if not st.get("FAIL") else RED)
            ratio = cov.get("ratio", 0)
            print(f"  {col}{mid:28}{OFF} {cov.get('delivered', 0):>4}/{cov.get('requested', 0):<4} "
                  f"{ratio:>4.0%}  charts: {dict(st)}   insights: {len(says)}/{len(interps)}")
            for s in says:
                print(f"      {DIM}→ {s[:104]}{OFF}")
            model_rows.append((pid, mid, ratio, st, len(says), len(interps)))

    n_charts = sum(tally[k] for k in ("family", "raw", "REFUSED", "FAIL"))
    print(f"\n{BOLD}{'=' * 92}{OFF}")
    print(f"{BOLD}CHARTS — {n_charts} across {len(model_rows)} models{OFF}")
    for k, col in (("family", GREEN), ("raw", AMBER), ("REFUSED", RED), ("FAIL", RED)):
        if tally[k]:
            pct = 100 * tally[k] / n_charts if n_charts else 0
            print(f"  {col}{k:9}{OFF} {tally[k]:>4}  {pct:5.1f}%")
    if tally["model_fail"]:
        print(f"  {RED}model_fail{OFF} {tally['model_fail']}")

    print(f"\n{BOLD}INSIGHTS — {fired_total}/{declared_total} authored interpretations fire on today's data{OFF}")
    if dead_interps:
        print(f"  {AMBER}silent models (interpretations declared, none true today): {len(dead_interps)}{OFF}")
        for d in dead_interps:
            print(f"    {d}")
    print()


if __name__ == "__main__":
    main()
