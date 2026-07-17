"""Judge the CATALOG's own hand-authored claims against what the models actually produce.

Wiring the fact sheet into the writer fixed the LLM's prose and left a hole exactly where nobody was
looking. The false superlative kept shipping — as a chart caption:

    catalog/graph/policy_stance.yaml:64
    insight: "... the sharp swing to the most restrictive setting relative to r* since the GFC"

rendered verbatim under a chart of a series that peaked in 2024 and has faded to +0.18pp since.

These strings are the same failure as the narrator's, one layer up. A human wrote them once, against
the data as it stood that day, and they have been asserted as fact under every chart ever since. The
data moved; the caption did not. Nothing checks them:

    - the in-loop Judge sees the AUTHORED prose only — captions are injected at render time
    - the writer could not fix one anyway: it did not write them and cannot edit them
    - `interpretations[].says` is worse — it fires on a `when` guard and speaks in the model's voice

28 models, 115 captions, 46 interpretations. This runs the same Judge over all of them: the LLM
extracts the typed claims, arithmetic settles them against model_output_point. Output is a list of
catalog strings that contradict their own model — for a human to fix in the YAML, which is the only
place they can be fixed.

    ~/venv/bin/python scripts/catalog_audit.py                 # every model
    ~/venv/bin/python scripts/catalog_audit.py --model policy_stance
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.graph_corpus import run_model  # noqa: E402
from render.judge.graph import judge_article  # noqa: E402
from render.model_store import record_run  # noqa: E402
from render.writer import _active_says  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"


def _claims_text(spec: dict, run: dict) -> str:
    """Every hand-authored assertion this model is CURRENTLY making about its own output.

    Judged together rather than one-by-one: a caption is a fragment ("the 2022 spike"), and the
    extractor binds a fragment to an output far more reliably with its siblings for context.

    THE TWO KINDS ARE NOT THE SAME, and conflating them convicts honest work:

      charts[].insight        — UNCONDITIONAL. Rendered under the chart on every run, whatever the
                                data says. Judging it against today is exactly right.
      interpretations[].says  — CONDITIONAL on its `when` guard. commodity_momentum's "the complex is
                                broadly trending down" is guarded by `breadth < -0.5`; breadth is
                                positive today, so the string does not ship — and checking it against
                                a rising market flags a sentence that is correct for the state it
                                describes. That is a category error: testing a consequent in a world
                                where the antecedent is false.

    So only the interpretations the model is actually voicing are judged. `_active_says` already
    evaluates the guards properly (inputs + outputs in scope, raises made loud), so it is reused
    rather than reimplemented.
    """
    lines = []
    for c in spec.get("charts") or []:
        if ins := (c.get("insight") or "").strip():
            lines.append(f"{ins}.")
    for says in _active_says(run.get("meta") or {}, run.get("latest")):
        lines.append(f"{says}.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="audit one model_id")
    ap.add_argument("--instance", default="US")
    args = ap.parse_args()

    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")

    specs = {}
    for f in sorted(GRAPH_DIR.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        if isinstance(d, dict) and (mid := d.get("model_id")):
            specs[mid] = d
    if args.model:
        specs = {args.model: specs[args.model]}

    audited = flagged = skipped = 0
    findings: list[tuple[str, str, str]] = []

    for mid, spec in specs.items():
        try:
            run = run_model(mid, conn, instance=args.instance)
            rid = record_run(conn, run, instance=args.instance)
        except Exception as exc:
            # A model that will not execute is a finding in its own right, not a silent skip: its
            # captions are shipping unchecked and will keep shipping.
            print(f"SKIP  {mid:28} cannot execute — its claims stay UNCHECKED: "
                  f"{type(exc).__name__}: {str(exc)[:70]}", file=sys.stderr)
            skipped += 1
            continue
        if not rid:
            print(f"SKIP  {mid:28} produced no output — claims stay UNCHECKED", file=sys.stderr)
            skipped += 1
            continue

        text = _claims_text(spec, run)
        if not text.strip():
            continue
        audited += 1
        st = judge_article(text, {mid: rid}, conn)
        bad = st.get("failures") or []
        n = len(st.get("claims") or [])
        if bad:
            flagged += len(bad)
            print(f"FAIL  {mid:28} {len(bad)}/{n} claims contradict the model")
            for v in bad:
                print(f"        “{v.quote[:78]}”\n          {v.detail}")
                findings.append((mid, v.quote, v.detail))
        else:
            print(f"ok    {mid:28} {n} claims, all grounded")

    print(f"\n{audited} models audited, {skipped} unauditable, {flagged} catalog claims contradict "
          f"their own model.")
    if findings:
        print("\nThese are HAND-AUTHORED strings in catalog/graph/*.yaml. They ship as chart captions "
              "and model voice-overs. Fix them in the YAML — the writer cannot: it never wrote them.")
    sys.exit(0)


if __name__ == "__main__":
    main()
