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

# A relationship (scatter/pearson) IS the cloud of points. Below this many valid pairs there is no
# cloud — a 1- or 2-dot "scatter" is worse than no chart (it reads as a finished figure but says
# nothing, and mislabels its own time ramp). The polished relationship family already refuses under
# this floor; the raw fallback must refuse too, so a data-starved relationship is OMITTED everywhere
# rather than shipped broken. Matches families/relationship.py's `< 10` lint. (Owner-flagged: the
# return_distribution Pearson diagram had 2 points because ^GSPC has only ~1yr of history — task #49.)
_MIN_REL_POINTS = 10


def _n_valid_pairs(xs, ys) -> int:
    return sum(1 for x, y in zip(xs, ys)
               if isinstance(x, (int, float)) and isinstance(y, (int, float))
               and x == x and y == y)   # x==x screens NaN


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


def render_chart(ax, chart: dict, history: list, *, fig=None, coverage: dict | None = None) -> None:
    dc = chart["data_contract"]
    kind = dc["kind"]

    # THE COVERAGE GATE. `coverage` comes from graph_corpus.run_model, which has always known both
    # numbers — how many as-of dates were requested, and how many the executor actually delivered —
    # and threw the first away. run_history skips any date where an input is thin; honest per point,
    # invisible in aggregate. That is how reaction_function shipped an 8-point chart captioned
    # "through the tightening cycle" out of 65 requested, with every gate green.
    #
    # Refusing here is NOT the answer to a data gap — a refusal that ends there is just the failure
    # wearing the costume of rigour (directive #1). It is the answer to a MISLEADING CHART: the
    # reader must never be shown a starved window drawn as though it were a choice. The gap itself is
    # an acquisition task, and the named reason below is what routes it there —
    # scripts/data_fitness.py turns it into a plan.
    if coverage and coverage.get("starved"):
        raise ValueError(
            f"DATA STARVED — refusing to draw {chart.get('id')!r}: asked for "
            f"{coverage['requested']} as-of dates from {coverage['asked_from']}, the executor "
            f"delivered {coverage['delivered']} ({coverage['ratio']:.0%}, {coverage['first']} → "
            f"{coverage['last']}). This chart would read as a deliberate window. "
            f"Run `python scripts/data_fitness.py` for the binding series and the remedy.")

    latest = history[-1]
    # The chart's `id` is the human title. The ontology `role`
    # (OUTCOME/INPUT/CONSEQUENCE) is internal metadata — never rendered.
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
                             ylabel=dc.get("ylabel", "%"), zero_line=dc.get("zero_line", False),
                             robust_ylim=dc.get("robust_ylim", False),
                             hline=dc.get("hline"), hline_label=dc.get("hline_label"))

    elif kind == "gap_series":
        x = list(range(len(history)))
        sub = dc.get("subtrahend")
        gap = [(_val(r, dc["minuend"]) - (_val(r, sub) if sub else 0.0)) for r in history]
        if cj == "diverging":
            charts.diverging_area(ax, x, gap, label=dc.get("label", "gap"),
                                  xticklabels=_xlabels(history), title=title,
                                  ylabel=dc.get("ylabel", "pp"),
                                  pos_label=dc.get("pos_label", "above"),
                                  neg_label=dc.get("neg_label", "below"))
        else:
            charts.overlay_lines(ax, x, [(dc.get("label", "gap"), gap, "solid")],
                                 xticklabels=_xlabels(history), title=title,
                                 ylabel=dc.get("ylabel", "pp"), zero_line=True)

    elif kind == "heatmap":
        # rows = a cross-section (tenors, ratings, ...); cols = time. The whole surface at once.
        matrix = [_hist(history, r["from"]) for r in dc["rows"]]
        row_labels = [r["label"] for r in dc["rows"]]
        charts.matrix_heatmap(ax, matrix, row_labels, _xlabels(history), color_job=cj,
                              title=title, cbar_label=dc.get("cbar_label", ""), fig=fig,
                              fmt=dc.get("fmt"))

    elif kind == "curve_snapshot":
        # the term structure at several dates — its SHAPE and how it shifted
        tenors = dc["tenor_labels"]
        refs = dc["refs"]
        curves = []
        for lb in dc.get("lookbacks", [{"label": "now", "k": 0, "style": "solid"}]):
            run = history[-1 - lb["k"]] if len(history) > lb["k"] else history[0]
            curves.append((lb.get("label", str(run.as_of)[:10]),
                           [_val(run, ref) for ref in refs], lb.get("style", "solid")))
        charts.curve_snapshot(ax, tenors, curves, title=title, ylabel=dc.get("ylabel", "value"),
                              xlabel=dc.get("xlabel", "tenor"))

    elif kind == "stacked":
        x = list(range(len(history)))
        layers = [(s["label"], _hist(history, s["from"])) for s in dc["layers"]]
        charts.stacked_area(ax, x, layers, xticklabels=_xlabels(history), title=title,
                            ylabel=dc.get("ylabel", "%"),
                            total_label=dc.get("total_label"))

    elif kind == "pearson":
        # the Pearson β1-β2 diagram — the return distribution's rolling (skew², kurtosis) over time
        xs = _hist(history, dc["x"])
        ys = _hist(history, dc["y"])
        if _n_valid_pairs(xs, ys) < _MIN_REL_POINTS:
            raise ValueError(f"pearson {title!r}: only {_n_valid_pairs(xs, ys)} valid points "
                             f"(< {_MIN_REL_POINTS}) — refusing a data-starved diagram")
        dates = [r.as_of for r in history]   # real observation dates → month+year colorbar ticks
        charts.pearson_diagram(ax, xs, ys, title=title, fig=fig,
                               cbar_label=dc.get("cbar_label", "time"), dates=dates)

    elif kind == "scatter":
        # a two-variable RELATIONSHIP across history (Phillips, Okun, CAPM SML, Beveridge) — the
        # message is the fit, not the time axis; points shade early->late, path draws the loops.
        xs = _hist(history, dc["x"])
        ys = _hist(history, dc["y"])
        if _n_valid_pairs(xs, ys) < _MIN_REL_POINTS:
            raise ValueError(f"scatter {title!r}: only {_n_valid_pairs(xs, ys)} valid points "
                             f"(< {_MIN_REL_POINTS}) — refusing a data-starved cloud")
        charts.scatter_fit(ax, xs, ys, title=title,
                           xlabel=dc.get("xlabel", "x"), ylabel=dc.get("ylabel", "y"),
                           fit=dc.get("fit", True), path=dc.get("path", False),
                           time_colour=dc.get("time_colour", True),
                           cbar_label=dc.get("cbar_label", "time"), fig=fig)

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
        render_chart(ax, ch, history, fig=fig)
    if suptitle:
        fig.suptitle(suptitle, fontsize=12.5, y=1.0, fontweight="bold")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
