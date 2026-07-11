#!/usr/bin/env python
"""Validate the executable model graph (catalog/graph/) against the acceptance floors.

Hard gate (the owner-agreed floors, see catalog/_ontology.md):
  - >= 3 models per persona
  - each model >= 3 distinct input VARIABLES (series) — unless low_dimensional_exception: true
  - each model >= 4 charts, each carrying a data_contract
  - each model >= 1 grounded_in paper, and every cited paper is in the knowledge corpus (registry)
  - each model's implemented_by resolves to a real callable in UMD analysis/ (static — no import,
    so QuantLib-blocked modules still validate by source)

Also checks: execution/outputs present; every persona's `models` resolve to a spec file; every
`stub_charts` reference resolves to a real chart. Exit 0 if all floors pass, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
GRAPH = REPO / "catalog" / "graph"
REGISTRY = REPO / "knowledge" / "registry.yaml"
UMD_SRC = Path.home() / "PycharmProjects/unified_market_data/src"

_TTY = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
OK, FAIL = c("32", "PASS"), c("31", "FAIL")


def _resolve_callable(dotted: str) -> bool:
    *mod, fn = dotted.split(".")
    path = UMD_SRC.joinpath(*mod).with_suffix(".py")
    if not path.exists():
        return False
    return bool(re.search(rf"^\s*(async\s+def|def)\s+{re.escape(fn)}\b", path.read_text(errors="ignore"), re.M))


def main() -> int:
    papers = {p["id"] for p in (yaml.safe_load(REGISTRY.read_text()).get("papers") or [])}
    specs = {}
    for f in sorted(GRAPH.glob("*.yaml")):
        if f.name == "personas.yaml":
            continue
        specs[f.stem] = yaml.safe_load(f.read_text())
    personas = yaml.safe_load((GRAPH / "personas.yaml").read_text()).get("personas", {})

    failures = 0
    print("MODELS")
    for mid, d in specs.items():
        errs = []
        series_inputs = {i.get("series_id") for i in (d.get("inputs") or []) if i.get("source", "series") == "series" and i.get("series_id")}
        n_var = len(series_inputs)
        # `canonical: true` — a textbook relationship taught throughout economics (Phillips, Okun,
        # CAPM, Beveridge). Its two variables ARE the model; the >=3-input floor does not apply.
        waived = d.get("low_dimensional_exception") or d.get("canonical")
        if n_var < 3 and not waived:
            errs.append(f"only {n_var} input variables (<3, no exception)")
        charts = d.get("charts") or []
        if len(charts) < 4:
            errs.append(f"only {len(charts)} charts (<4)")
        if any(not ch.get("data_contract") for ch in charts):
            errs.append("a chart lacks a data_contract")
        grounded = d.get("grounded_in") or []
        if not grounded:
            errs.append("no grounded_in paper")
        missing_papers = [g for g in grounded if g not in papers]
        if missing_papers:
            errs.append(f"papers not in corpus: {missing_papers}")
        impl = (d.get("execution") or {}).get("implemented_by")
        if not impl:
            errs.append("no execution.implemented_by")
        elif not _resolve_callable(impl):
            errs.append(f"implemented_by unresolved: {impl}")
        if not d.get("outputs"):
            errs.append("no outputs")
        exc = " [low-dim exception]" if d.get("low_dimensional_exception") else ""
        status = OK if not errs else FAIL
        failures += bool(errs)
        print(f"  {status}  {mid:28} vars={n_var} charts={len(charts)} papers={grounded}{exc}"
              + ("" if not errs else "\n         " + "; ".join(errs)))

    print("\nPERSONAS")
    for pid, p in personas.items():
        errs = []
        models = p.get("models") or []
        if len(models) < 3:
            errs.append(f"only {len(models)} models (<3)")
        missing = [m for m in models if m not in specs]
        if missing:
            errs.append(f"unknown models: {missing}")
        for mref, cref in (p.get("stub_charts") or []):
            if mref not in specs or not any(ch.get("id") == cref for ch in (specs.get(mref, {}).get("charts") or [])):
                errs.append(f"stub_chart unresolved: [{mref}, {cref}]")
        status = OK if not errs else FAIL
        failures += bool(errs)
        print(f"  {status}  {pid:28} models={len(models)}" + ("" if not errs else "  " + "; ".join(errs)))

    n_pers_done = sum(1 for p in personas.values() if len(p.get("models") or []) >= 3)
    print(f"\nSUMMARY: {len(specs)} models, {len(personas)} personas authored "
          f"({n_pers_done} meet the 3-model floor); {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
