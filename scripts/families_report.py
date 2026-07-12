"""Structure-family coverage harness: how far the ACS now escapes line-dominance.

Routes every authored chart in the catalog to a structure-family by its data_contract.kind,
and for the rich families (decomposition / relationship / surface) executes the model and
confirms the chart renders LINT-CLEAN through the deterministic renderer. Reports the family
distribution, the rich-vs-trend share (the escape-from-lines metric), lint-pass rate, and
persona coverage — the objective "capable + generalises" numbers.

    ~/venv/bin/python scripts/families_report.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render import graph_corpus                                              # noqa: E402
from render.studio.families import decomposition as dc                       # noqa: E402
from render.studio.families import relationship as rel                       # noqa: E402
from render.studio.families import surface as surf                           # noqa: E402

GRAPH_DIR = Path(__file__).resolve().parents[1] / "catalog" / "graph"

# data_contract.kind → (family label, is it a "rich" non-line form?)
KIND_FAMILY = {
    "decomposition": ("decomposition", True), "stacked": ("decomposition*", True),
    "scatter": ("relationship", True), "pearson": ("relationship", True),
    "heatmap": ("surface", True), "curve_snapshot": ("surface*", True),
    "series": ("trend/line", False), "gap_series": ("trend/line", False),
    "named_values": ("bar", False), "distribution": ("distribution", True),
    "qq": ("distribution", True),
}
VERIFIERS = {"decomposition": dc.spec_from_run, "scatter": rel.spec_from_run,
             "pearson": rel.spec_from_run, "heatmap": surf.spec_from_run}


def main():
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    models = sorted(p.stem for p in GRAPH_DIR.glob("*.yaml") if p.stem != "personas")
    fam_counts = Counter()
    rich = lint_ok = lint_fail = 0
    total = 0
    personas_rich = defaultdict(set)
    runs: dict[str, dict] = {}

    for mid in models:
        m = yaml.safe_load((GRAPH_DIR / f"{mid}.yaml").read_text())
        persona = m.get("persona", "?")
        for chart in m.get("charts", []):
            total += 1
            kind = (chart.get("data_contract", {}) or {}).get("kind", "series")
            fam, is_rich = KIND_FAMILY.get(kind, ("other", False))
            fam_counts[fam] += 1
            if not is_rich:
                continue
            rich += 1
            verifier = VERIFIERS.get(kind)
            if verifier is None:               # rich-shaped but no deterministic family yet
                continue
            try:
                if mid not in runs:
                    runs[mid] = graph_corpus.run_model(mid, conn)
                built = verifier(m, runs[mid], chart["id"])
                if built is None:
                    lint_fail += 1; continue
                # exercise the lint (renderers raise on any violation)
                if kind in ("scatter", "pearson"):
                    df, spec = built; probs = rel.lint_relationship(spec, df)
                elif kind == "heatmap":
                    _dates, mat, spec = built; probs = surf.lint_surface(spec, mat)
                else:
                    df, spec = built; probs = dc.lint_decomposition(spec, df)
                if probs:
                    lint_fail += 1
                else:
                    lint_ok += 1; personas_rich[persona].add(fam)
            except Exception:
                lint_fail += 1

    print("=" * 66)
    print("STRUCTURE-FAMILY COVERAGE  (authored charts across the catalog)")
    print("=" * 66)
    print(f"models: {len(models)}    authored charts: {total}\n")
    print("family distribution:")
    for fam, c in fam_counts.most_common():
        bar = "█" * c
        print(f"  {fam:16} {c:3}  {bar}")
    rich_share = rich / total if total else 0
    print(f"\nrich (non-line) forms: {rich}/{total} = {rich_share:.0%}   "
          f"trend/line+bar: {(fam_counts['trend/line']+fam_counts['bar'])}/{total}")
    ver = lint_ok + lint_fail
    print(f"deterministic-family verify: {lint_ok}/{ver} render LINT-CLEAN "
          f"({lint_fail} unrenderable — usually a data gap)")
    print("\npersona → rich families proven:")
    for p, fams in sorted(personas_rich.items()):
        print(f"  {p:26} {', '.join(sorted(fams))}")


if __name__ == "__main__":
    main()
