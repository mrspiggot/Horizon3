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
_SINGLE = re.compile(r'^(output|input):([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?$')


def _parse_ref(s: str):
    m = _SINGLE.match((s or "").strip())
    return (m.group(1), m.group(2), m.group(3)) if m else None


def _label(field: str, state: str | None) -> str:
    return field.replace("_", " ") + (f" ({state})" if state and state != "level" else "")


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


# ── shape-aware extractors: each preserves the authored insight's STRUCTURE ────────────────────
# Each returns (rows, series_field, insight_type, form_hint) or None. The structure is what lets a
# complex mark bind — a scatter needs two quantitative columns, a surface an item×time matrix, etc.
# Line-dominance was caused by melting everything to {date, series, value}; these stop that.

def _shape_relationship(dc: dict, history: list):
    """scatter / pearson → WIDE rows {x_col, y_col, order, date}: two quantitative axes."""
    xr, yr = _parse_ref(dc.get("x", "")), _parse_ref(dc.get("y", ""))
    if not xr or not yr:
        return None
    xcol, ycol = _label(xr[1], xr[2]), _label(yr[1], yr[2])
    rows = []
    for i, r in enumerate(history):
        xv, yv = _value(r, *xr), _value(r, *yr)
        if xv is not None and yv is not None:
            rows.append({xcol: round(float(xv), 4), ycol: round(float(yv), 4),
                         "order": i, "date": str(r.as_of)[:10]})
    hint = (f"RELATIONSHIP: plot '{xcol}' (x) against '{ycol}' (y) as a connected_scatter — time-ordered "
            f"by 'order'/'date', colour early→late, mark the start/end — or a point scatter with a fit line. "
            f"NEVER two lines over time; the relationship IS the message.")
    return rows, None, "relationship", hint


def _shape_surface(dc: dict, history: list):
    """heatmap → item×time matrix rows {item, date, value}."""
    items = [(r.get("label"), _parse_ref(r.get("from", ""))) for r in (dc.get("rows") or [])]
    items = [(lab, ref) for lab, ref in items if ref]
    if not items:
        return None
    rows = []
    for r in history:
        d = str(r.as_of)[:10]
        for lab, ref in items:
            v = _value(r, *ref)
            if v is not None:
                rows.append({"item": lab, "date": d, "value": round(float(v), 4)})
    hint = ("SURFACE: an item × time matrix. Draw a heatmap (x=date, y=item, colour=value; diverging colour "
            "if the value is signed) or small multiples (one panel per item). Not a tangle of lines.")
    return rows, "item", "surface", hint


def _shape_cross_section(dc: dict, history: list):
    """curve_snapshot → cross-section rows {item, value, snapshot} across ordered items at k snapshots."""
    labels = dc.get("tenor_labels") or []
    refs = [_parse_ref(x) for x in (dc.get("refs") or [])]
    looks = dc.get("lookbacks") or [{"label": "now", "k": 0}]
    if not labels or not refs or len(labels) != len(refs):
        return None
    rows = []
    for lb in looks:
        idx = len(history) - 1 - int(lb.get("k", 0))
        if idx < 0:
            continue
        r = history[idx]
        for lab, ref in zip(labels, refs):
            if not ref:
                continue
            v = _value(r, *ref)
            if v is not None:
                rows.append({"item": lab, "value": round(float(v), 4), "snapshot": lb.get("label", "now")})
    hint = ("CROSS-SECTION across ordered items (tenors/rungs) at one or a few snapshots. Draw the curve as a "
            "line/point over the items, or a slope/dumbbell to compare two snapshots. 'item' is ordinal, not time.")
    return rows, "snapshot", "cross_section", hint


def _shape_decomposition(dc: dict, history: list):
    """stacked → {date, component, value} that sum to a total."""
    layers = [(l.get("label"), _parse_ref(l.get("from", ""))) for l in (dc.get("layers") or [])]
    layers = [(lab, ref) for lab, ref in layers if ref]
    if not layers:
        return None
    rows = []
    for r in history:
        d = str(r.as_of)[:10]
        for lab, ref in layers:
            v = _value(r, *ref)
            if v is not None:
                rows.append({"date": d, "component": lab, "value": round(float(v), 4)})
    hint = ("DECOMPOSITION: the components SUM to a total. Draw a stacked_area with a total line (components "
            "may be signed) or a waterfall — NOT separate lines.")
    return rows, "component", "decomposition", hint


def _shape_series(dc: dict, history: list):
    """series / gap_series / named_values / anything else → {date, series, value} (the trend melt)."""
    refs = _refs(dc)
    if not refs:
        return None
    rows = []
    for r in history:
        d = str(r.as_of)[:10]
        for kind, field, state in refs:
            v = _value(r, kind, field, state)
            if v is not None:
                rows.append({"date": d, "series": _label(field, state), "value": round(float(v), 4)})
    if not rows:
        return None
    n = len({x["series"] for x in rows})
    itype = "state_space" if any(s for _, _, s in refs if s in ("zscore", "percentile", "direction", "acceleration")) else "trend"
    if itype == "state_space":
        hint = ("STATE-SPACE: these are §10 state dimensions. Consider a quadrant/momentum map, or drive "
                "diverging colour and ±1σ threshold reference-lines off the z-score/percentile.")
    elif n <= 3:
        hint = ("TREND: one or a few series over time — a line/area/gap is legitimate, but EARN it: add "
                "reference/threshold lines, regime/event shading, direct labels and a thesis headline.")
    else:
        hint = "TREND with many series — prefer small multiples or a heatmap if they share a scale."
    return rows, "series", itype, hint


_SHAPERS = {
    "scatter": _shape_relationship, "pearson": _shape_relationship,
    "heatmap": _shape_surface, "curve_snapshot": _shape_cross_section,
    "stacked": _shape_decomposition,
}


def brief_for_chart(persona: str, decision: str, model_id: str, chart_id: str, run: dict) -> InsightBrief | None:
    """Build a STRUCTURE-PRESERVING Studio brief from one authored chart: classify the insight type
    from the authored data_contract.kind and shape the data so the matching complex form can bind."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    shaper = _SHAPERS.get(dc.get("kind", ""))
    res = (shaper(dc, history) if shaper else None) or _shape_series(dc, history)
    if not res or not res[0]:
        return None
    rows, series_field, insight_type, form_hint = res
    meta = run["meta"]
    insight = " ".join((chart.get("insight") or "").split())
    interp = f"{chart_id}. {insight}" if insight else chart_id
    return InsightBrief(
        persona=persona, decision=decision, model_id=model_id, papers=(meta.get("grounded_in") or []),
        interpretation=interp, insight_type=insight_type, form_hint=form_hint,
        profile=profile_rows(rows, series_field=series_field), rows=rows)


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
        results.append({"model_id": model_id, "chart_id": chart_id, "insight_type": brief.insight_type,
                        "mark": (ch.mark if ch else None), "title": (ch.title if ch else None),
                        "png": final.get("png_path"), "visual_ok": final.get("visual_ok"),
                        "judge_pass": final.get("judge_pass")})
    return results
