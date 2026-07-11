"""Graph-driven renderer — turn a model's EXECUTED outputs into its declared insight charts.

Given a model's run history (a list of `ModelRun` from the Executor) and its `Chart` specs
(chart_type + data_contract + interpretation), this shapes the model's OUTPUTS and input-states to
each chart's data contract and renders via the deterministic `render/charts.py` primitives. Charts
render the model's outputs/interpretations — never a raw series or a tautology (§06). No number is
authored here; every value comes from a `ModelRun`.

A `data_contract` reference is one of: "output:<name>" | "input:<id>[.<component>]" | "as_of" | literal.
Supported `kind`s: named_values (bar snapshot), series (lines over history), gap_series (a difference
over history around zero).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import charts  # noqa: E402


def _val(run, ref):
    if not isinstance(ref, str):
        return ref
    if ref == "as_of":
        return run.as_of
    if ref.startswith("output:"):
        return run.outputs.get(ref[len("output:"):])
    if ref.startswith("input:"):
        body = ref[len("input:"):]
        iid, _, comp = body.partition(".")
        obj = run.inputs.get(iid)
        if obj is None:
            return None
        if isinstance(obj, (int, float)):
            return obj                       # a derived scalar input
        return getattr(obj, comp or "level", None)   # a §10 State component
    return ref                               # literal


def _hist(history, ref):
    return [_val(r, ref) for r in history]


def _xlabels(history):
    return [str(r.as_of)[:7] if r.as_of else "" for r in history]


def render_chart(ax, chart: dict, history: list) -> None:
    dc = chart["data_contract"]
    kind = dc["kind"]
    latest = history[-1]
    title = chart.get("id")
    cj = chart.get("color_job", "diverging")

    if kind == "named_values":
        labels = dc["labels"]
        values = [_val(latest, v) for v in dc["values"]]
        charts.bar(ax, labels, values, color_job=cj, title=title, ylabel=dc.get("ylabel", "%"),
                   ref=_val(latest, dc["ref"]) if dc.get("ref") else None)

    elif kind == "series":
        x = list(range(len(history)))
        series = [(s["label"], _hist(history, s["from"]), s.get("style", "solid"))
                  for s in dc["series"]]
        charts.overlay_lines(ax, x, series, xticklabels=_xlabels(history), title=title,
                             ylabel=dc.get("ylabel", "%"), zero_line=dc.get("zero_line", False))

    elif kind == "gap_series":
        x = list(range(len(history)))
        gap = [(_val(r, dc["minuend"]) - _val(r, dc["subtrahend"])) for r in history]
        charts.overlay_lines(ax, x, [(dc.get("label", "gap"), gap, "solid")],
                             xticklabels=_xlabels(history), title=title,
                             ylabel=dc.get("ylabel", "pp"), zero_line=True)

    else:
        raise ValueError(f"unknown data_contract kind {kind!r}")


def render_model(history: list, charts_spec: list[dict], out_path: str, *, suptitle: str | None = None) -> str:
    """Render every chart in `charts_spec` from the model's run `history`, composed into one figure."""
    if not history:
        raise ValueError("no runs to render (the model produced no outputs)")
    n = len(charts_spec)
    ncol = 2 if n > 1 else 1
    nrow = (n + ncol - 1) // ncol
    fig = plt.figure(figsize=(8.2 * ncol, 5.2 * nrow))
    for i, ch in enumerate(charts_spec):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        render_chart(ax, ch, history)
    if suptitle:
        fig.suptitle(suptitle, fontsize=12.5, y=1.0, fontweight="bold")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
