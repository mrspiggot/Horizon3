"""Bridge: an executed graph model → a Studio InsightBrief → a Studio-designed chart.

Division of labour (the corrected one): the INSIGHT — which output/input fields to show and
what they MEAN — is an authored modelling decision that already lives in the graph (each model
chart carries an `insight` line and a `data_contract` naming its fields). The Studio's job is
the FORM — the mark, encoding and annotations that carry that insight. So this bridge does NOT
invent insights; it reads each authored stub chart, pulls its fields from the executed history,
hands the Studio the authored insight text + the real data, and lets the agent graph choose how
to draw it (which may beat the hand-coded form). Numbers come only from the executed run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .. import graph_corpus
from .graph import run_studio
from .insight import InsightBrief, profile_rows

GRAPH_DIR = Path(__file__).resolve().parents[2] / "catalog" / "graph"
_REF = re.compile(r'"(output|input):([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?"')


def _refs(data_contract: dict) -> list[tuple[str, str, str | None]]:
    """Extract (kind, field, state) triples referenced by a chart's data_contract, in order,
    deduped. kind ∈ {output, input}; state applies to inputs (level/zscore/…), default level."""
    seen, out = set(), []
    for m in _REF.finditer(json.dumps(data_contract)):
        key = (m.group(1), m.group(2), m.group(3))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _value(run_point, kind: str, field: str, state: str | None):
    if kind == "output":
        return run_point.outputs.get(field)
    obj = run_point.inputs.get(field)
    if obj is None:
        return None
    return getattr(obj, state or "level", None)


def brief_for_chart(persona: str, decision: str, model_id: str, chart_id: str, run: dict) -> InsightBrief | None:
    """Build a Studio brief from ONE authored chart of a model: its `insight` text + the fields
    its data_contract names, pulled from the executed history."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    refs = _refs(chart.get("data_contract", {}))
    if not refs:
        return None
    rows = []
    for r in history:
        d = str(r.as_of)[:10]
        for kind, field, state in refs:
            v = _value(r, kind, field, state)
            if v is not None:
                label = field.replace("_", " ") + (f" ({state})" if state and state != "level" else "")
                rows.append({"date": d, "series": label, "value": round(float(v), 4)})
    if not rows:
        return None
    meta = run["meta"]
    papers = meta.get("grounded_in") or []
    insight = " ".join((chart.get("insight") or "").split())
    interp = f"{chart_id}. {insight}" if insight else chart_id
    n_series = len({r["series"] for r in rows})
    # The authored data_contract kind is the model author's intent — a strong prior on the form
    # (e.g. 'stacked' = a genuine part-to-whole; 'gap_series' = a signed difference). The Studio
    # still designs the encoding, but should honour a declared composition.
    kind = (chart.get("data_contract") or {}).get("kind", "")
    prior = ""
    if kind == "stacked":
        prior = (" The authored form is a STACKED composition: these fields sum to a total — draw it as "
                 "a stacked_area with a total line (components may be signed), NOT as separate lines.")
    elif kind == "gap_series":
        prior = " The authored form is a signed gap around a baseline (a filled area above/below zero)."
    note = (f"{n_series} field(s) the authored insight names, over "
            f"{'time' if any(rr.get('date') for rr in rows) else 'items'}. Design the FORM that "
            f"carries the insight." + prior)
    return InsightBrief(persona=persona, decision=decision, model_id=model_id, papers=papers,
                        interpretation=interp, profile=profile_rows(rows, series_field="series", note=note),
                        rows=rows)


def studio_charts_for_persona(persona_id: str, conn, out_dir: str) -> list[dict]:
    """Design each of a persona's authored stub charts with the Studio (form chosen by the graph)."""
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]
    p = personas[persona_id]
    runs: dict[str, dict] = {}
    results = []
    for i, (model_id, chart_id) in enumerate(p["stub_charts"]):
        if model_id not in runs:
            runs[model_id] = graph_corpus.run_model(model_id, conn)
        brief = brief_for_chart(p["name"], p.get("decision", ""), model_id, chart_id, runs[model_id])
        if brief is None:
            results.append({"model_id": model_id, "chart_id": chart_id, "error": "no data/fields"})
            continue
        d = Path(out_dir) / f"{i}_{model_id}"
        d.mkdir(parents=True, exist_ok=True)
        try:
            final = run_studio(brief, str(d), max_iterations=3)
        except Exception as exc:
            results.append({"model_id": model_id, "chart_id": chart_id,
                            "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            continue
        ch = final.get("chosen")
        results.append({"model_id": model_id, "chart_id": chart_id,
                        "mark": (ch.mark if ch else None), "title": (ch.title if ch else None),
                        "png": final.get("png_path"), "visual_ok": final.get("visual_ok"),
                        "judge_pass": final.get("judge_pass")})
    return results
