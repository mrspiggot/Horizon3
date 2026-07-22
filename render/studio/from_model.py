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
    # Reader labels, not raw DB column names: humanise() expands ig→IG, gz→GZ, ebp→"excess bond premium",
    # rf→"risk-free" and strips _pct/_pp suffixes, so a legend reads "GZ spread" not "gz spread". The v6
    # review flagged raw-column legends ("risk free pct", "sahm gap pp", "rf") across the batch.
    from ..infographic.from_persona import humanise
    return humanise(field) + (f" ({state})" if state and state != "level" else "")


def _authored_labels(dc: dict) -> dict:
    """field → author's display label, harvested from any {label, from} pairs in the data_contract, so a
    chart's own catalogued label wins over the humanised field name (the melt-to-series path dropped it)."""
    out: dict = {}
    for v in dc.values():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and item.get("label") and item.get("from"):
                    ref = _parse_ref(item["from"])
                    if ref:
                        out[ref[1]] = item["label"]
    return out


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
    if isinstance(obj, (int, float)):
        # A `source: derived` input resolves to a plain scalar, not a §10 State — there is no
        # component to index into. Without this, getattr(float, "level") returns None and EVERY
        # value silently becomes NaN, so any chart reading a derived input (reaction_function's
        # output gap, for one) dropped out of its family and fell back to the raw renderer. All
        # four families share this helper, so all four were blind to derived inputs.
        # from_graph._val has always had this branch; this is the studio path catching up.
        return obj
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
    authored = _authored_labels(dc)
    rows = []
    for r in history:
        d = str(r.as_of)[:10]
        for kind, field, state in refs:
            v = _value(r, kind, field, state)
            if v is not None:
                lab = authored.get(field) or _label(field, state)
                rows.append({"date": d, "series": lab, "value": round(float(v), 4)})
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


def compute_chart_insight(model: dict, run: dict, chart_id: str):
    """Run a chart's OWN analysis and return a ChartInsight (or None) — the computed structure the reader
    sees in the picture (regimes + slopes, later PCA loadings / feature importances), so the prose can be
    driven by it. DATA-CONTRACT / graph driven, so it generalises across models and every jurisdiction —
    never a per-persona hack. Never raises: the prose brief must not break on an analysis."""
    try:
        chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
        if not chart:
            return None
        dc = chart.get("data_contract") or {}
        transform = dc.get("transform") or ("regime" if dc.get("regimes") else "")
        if transform == "regime":
            from .families.relationship import regime_insight, spec_from_run
            built = spec_from_run(model, run, chart_id)
            if built:
                df, spec = built
                if spec.mode == "regime":
                    return regime_insight(df, spec)
            return None
        if transform == "pca":
            from .families.pca_biplot import pca_insight
            return pca_insight(model, run, chart_id)
        # Otherwise dispatch by the chart's structural KIND, so EVERY family yields its visual reading —
        # generalises across every model/persona/jurisdiction, not a hand-picked chart list.
        kind = dc.get("kind", "")
        if kind in ("series", "gap_series"):
            from .families.timeseries import timeseries_insight
            return timeseries_insight(model, run, chart_id)
        if kind in ("scatter", "pearson"):
            from .families.relationship import fit_insight
            return fit_insight(model, run, chart_id)
        if kind in ("decomposition", "stacked"):
            from .families.decomposition import decomposition_insight
            return decomposition_insight(model, run, chart_id)
        if kind == "heatmap":
            from .families.surface import surface_insight
            return surface_insight(model, run, chart_id)
        return None
    except Exception as exc:
        print(f"compute_chart_insight — {chart_id}: {type(exc).__name__}: {exc}",
              file=__import__("sys").stderr)
        return None


def brief_for_chart(persona: str, decision: str, model_id: str, chart_id: str, run: dict,
                    *, prose: str = "") -> InsightBrief | None:
    """Build a STRUCTURE-PRESERVING Studio brief from one authored chart: classify the insight type
    from the authored data_contract.kind and shape the data so the matching complex form can bind.
    When `prose` is given (the article section that shows this exhibit), it is folded into the
    interpretation so the framer picks the form the ARTICLE describes — a locus when the prose says the
    curve 'jumped outward', a recent window when the claim is about 'today'."""
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
    if prose:
        interp += (f"  ARTICLE PROSE that shows this exhibit (choose the form and window it describes; "
                   f"if it points at 'now/today/currently', prefer a recent-window view): {prose[:500]}")
    return InsightBrief(
        persona=persona, decision=decision, model_id=model_id, papers=(meta.get("grounded_in") or []),
        interpretation=interp, insight_type=insight_type, form_hint=form_hint,
        profile=profile_rows(rows, series_field=series_field), rows=rows,
        instance=run.get("instance") or "")


def brief_for_model_instances(persona: str, decision: str, model_id: str, chart_id: str, conn) -> InsightBrief | None:
    """Cross-JURISDICTION brief: run a jurisdiction-generic model across ALL its instances
    (Fed/ECB/BoE/BoJ…) and assemble a cross-sectional table with a `jurisdiction` column — the raw
    material for small multiples / a jurisdiction×time heatmap / a dumbbell where the DIVERGENCE is
    the insight. Wires the previously-latent graph_corpus.run_model_instances."""
    runs = graph_corpus.run_model_instances(model_id, conn)
    instances = runs.get("instances") or {}
    if len(instances) < 2:
        return None
    meta = runs["meta"]
    chart = next((c for c in (runs.get("charts") or []) if c.get("id") == chart_id), None)
    if chart is None:
        return None
    dc = chart.get("data_contract", {}) or {}
    kind = dc.get("kind", "")
    rows: list[dict] = []
    if kind in ("scatter", "pearson"):
        xr, yr = _parse_ref(dc.get("x", "")), _parse_ref(dc.get("y", ""))
        if not xr or not yr:
            return None
        xcol, ycol = _label(xr[1], xr[2]), _label(yr[1], yr[2])
        for jid, obj in instances.items():
            cb = obj.get("cb", jid)
            for i, r in enumerate(obj.get("history") or []):
                xv, yv = _value(r, *xr), _value(r, *yr)
                if xv is not None and yv is not None:
                    rows.append({xcol: round(float(xv), 4), ycol: round(float(yv), 4),
                                 "order": i, "jurisdiction": cb})
        itype = "relationship"
        hint = (f"CROSS-JURISDICTION RELATIONSHIP: '{xcol}' vs '{ycol}' for {len(instances)} central banks. "
                f"Draw SMALL MULTIPLES — one connected_scatter panel per 'jurisdiction' (set encoding.facet="
                f"'jurisdiction'), shared axes — so each bank's curve is comparable at a glance.")
    else:
        outs = meta.get("outputs") or []
        field = outs[0]["name"] if outs else None
        if not field:
            return None
        for jid, obj in instances.items():
            cb = obj.get("cb", jid)
            for r in obj.get("history") or []:
                v = r.outputs.get(field)
                if v is not None:
                    rows.append({"date": str(r.as_of)[:10], _label(field, None): round(float(v), 4),
                                 "jurisdiction": cb})
        itype = "cross_section"
        hint = (f"CROSS-JURISDICTION: '{_label(field, None)}' over time for {len(instances)} central banks. Draw "
                f"SMALL MULTIPLES (encoding.facet='jurisdiction'), a jurisdiction×time HEATMAP, or a DUMBBELL of "
                f"the latest value per bank — the DIVERGENCE across banks is the insight, not any one line.")
    if not rows:
        return None
    insight = " ".join((chart.get("insight") or "").split())
    interp = f"{chart_id} — compared across {len(instances)} central banks. {insight}"
    return InsightBrief(persona=persona, decision=decision, model_id=model_id, papers=(meta.get("grounded_in") or []),
                        interpretation=interp, insight_type=itype, form_hint=hint,
                        profile=profile_rows(rows, series_field="jurisdiction"), rows=rows)


def _det_cross_jurisdiction(brief, out_path: str) -> str | None:
    """Render a cross-jurisdiction TIME SERIES deterministically as one line per central bank — reliable,
    not a studio coin-toss. The agentic path mis-picked a per-date form here and exploded a Sahm-gap
    comparison to a 25,000px strip; a multi-line chart (x=date, y=value, one line per jurisdiction) is the
    honest, legible exhibit and reuses the P3-hardened compile path (≤12 series → clean legend)."""
    from .compile import compile_encoding
    from .encoding import ChartEncoding
    rows = brief.rows or []
    if not rows:
        return None
    yf = next((c for c in rows[0] if c not in ("date", "jurisdiction", "order")), None)
    if yf is None or "date" not in rows[0] or "jurisdiction" not in rows[0]:
        return None
    n_banks = len({r["jurisdiction"] for r in rows})
    enc = ChartEncoding(
        # title from the ACTUAL field plotted, not the model's chart-id (which may name several variables
        # a single-series render can't show — the 'inflation and unemployment' title over an unemployment-
        # only line is the very title-vs-chart mismatch this round is fixing).
        title=f"{yf} across {n_banks} central banks — one model, four economies",
        subtitle=f"{yf} — the same model run for {n_banks} central banks; the divergence is the point.",
        message="compare the same reading across jurisdictions",
        mark="line", color_job="categorical",
        encoding={"x": {"field": "date", "type": "temporal"},
                  "y": {"field": yf, "type": "quantitative", "title": yf},
                  "detail": {"field": "jurisdiction", "type": "nominal"},
                  "color": {"field": "jurisdiction", "type": "nominal"}},
        annotations={"label_last": True},
        data=rows)
    try:
        return compile_encoding(enc, out_path)
    except Exception:
        return None


def studio_cross_jurisdiction(model_id: str, chart_id: str, conn, out_dir: str,
                              persona: str = "Macro strategist", decision: str = "", *,
                              deterministic: bool = True) -> dict:
    """A cross-jurisdiction chart for one generic model's chart. Default: a DETERMINISTIC multi-line render
    (one line per central bank) — the agentic studio mis-picks the form for this shape. Set
    deterministic=False to let the Studio design it (scatter cross-sections may want small multiples)."""
    brief = brief_for_model_instances(persona, decision, model_id, chart_id, conn)
    if brief is None:
        return {"error": "not jurisdiction-generic or no data"}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if deterministic and brief.insight_type == "cross_section":
        png = _det_cross_jurisdiction(brief, str(Path(out_dir) / "studio_chart.png"))
        if png:
            return {"model_id": model_id, "chart_id": chart_id, "insight_type": brief.insight_type,
                    "mark": "line", "title": None, "png": png, "judge_pass": None, "deterministic": True}
    final = run_studio(brief, out_dir, max_iterations=3)
    ch = final.get("chosen")
    return {"model_id": model_id, "chart_id": chart_id, "insight_type": brief.insight_type,
            "mark": (ch.mark if ch else None), "title": (ch.title if ch else None),
            "png": final.get("png_path"), "judge_pass": final.get("judge_pass")}


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
