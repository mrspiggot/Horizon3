"""The TIME-SERIES structure-family: a model's quantity, read through time.

The most common shape in the catalog and, until now, the only one with no family — so it fell
through to the raw ``charts.py`` primitives. 45 ``series`` + 22 ``gap_series`` charts, 67 of 115,
rendered in stock matplotlib beside a polished dashboard. Every one of the eight editorial reviews
independently reported the same split ("polished dashboard; the rest default-matplotlib with generic
titles and redundant legends") — one dict entry, eight articles.

Two authored kinds, one renderer:

  * ``series``      — N labelled lines over time (levels, or several quantities compared).
  * ``gap_series``  — minuend − subtrahend as a signed area against zero: the quantity IS the gap
                      (policy stance vs r*, the term spread, the misery index, HY − IG).

What this fixes beyond typography, both reported repeatedly by reviewers:

  1. THE PHANTOM LEGEND. ``charts.diverging_area`` labels both fills unconditionally, so a series
     that cannot go negative (the misery index is unemployment + inflation) still printed a "below"
     swatch for a region that does not exist. ``fill_between`` registers a labelled handle even when
     its ``where`` mask is all-False. Here a sign only earns a legend entry if it has area.

  2. THE DROPPED LABELS. ``from_graph`` read ``pos_label``/``neg_label`` from inside
     ``data_contract``, but 14 of 15 catalogs author them one level up, as siblings of it — so ~20
     CORRECT authored labels ("restrictive (real rate > r*)" / "accommodative (real rate < r*)")
     were written and silently discarded in favour of the "above"/"below" defaults. The intent was
     always there; the plumbing dropped it. This reads chart level first, then the contract.

Every value comes from the executed run; this module authors none.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from ..from_model import _parse_ref, _value

INK, GRID = "#16161d", "#d7d7de"
_HALO = [pe.Stroke(linewidth=3.4, foreground="white"), pe.Normal()]
# An axis label is missing or it isn't. Do NOT try to detect "does this carry a unit" by matching a
# keyword list — that test cannot be written, because DIMENSIONLESS QUANTITIES ARE LEGITIMATE. Two
# earlier versions of this lint failed honest charts: first it rejected "percentage points", then,
# with a longer list, it still rejected `V/U - 1`, `WTI / Henry Hub`, `P(recession in 12m)`,
# `standard deviations`, `excess kurtosis (β2 - 3)` and `skewness` — ratios, probabilities and
# moments, every one correctly labelled. Each rejection silently dropped the chart back to the raw
# renderer, i.e. the lint was *causing* the defect it exists to prevent. A lint that fails honest
# work gets disabled, and then it protects nothing.
_PLACEHOLDER_YLABELS = {"", "-", "—", "value", "values", "y", "yaxis", "y-axis", "n/a", "na",
                        "data", "series", "number", "amount", "tbd"}

# Okabe-Ito, colourblind-safe. Same vocabulary as the other families so a persona's charts read as
# one system rather than four.
_TONE = {"neutral": "#B8C4CE", "base": "#B8C4CE", "cool": "#4C6EA8", "warm": "#D55E00",
         "green": "#009E73", "amber": "#D98A00", "violet": "#8B6BB1"}
_TONE_ORDER = ["#4C6EA8", "#D55E00", "#009E73", "#D98A00", "#8B6BB1", "#B8C4CE"]
_POS, _NEG = "#4C6EA8", "#D55E00"          # signed area: cool above zero, warm below

_MIN_POINTS = 10                            # a line through <10 points is a rumour, not a series
_STYLE = {"solid": "-", "dashed": (0, (5, 2)), "dotted": (0, (1, 2)), "dashdot": (0, (5, 2, 1, 2))}


@dataclass
class Line:
    key: str
    label: str
    color: str
    style: str = "solid"


@dataclass
class SeriesSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str
    lines: list[Line]
    source: str
    footer: str
    tick_years: int = 5
    zero_line: bool = False
    hline: float | None = None
    hline_label: str = ""
    # gap mode: render lines[0] as a signed area against zero instead of a plain line
    gap: bool = False
    pos_label: str = ""
    neg_label: str = ""
    callouts: list[dict] = field(default_factory=list)


def lint_timeseries(spec: SeriesSpec, df: pd.DataFrame) -> list[str]:
    """The craft contract. A violation blocks the render — a mislabelled axis or a data-starved
    line can never reach a human (Horizon2's failure mode)."""
    problems = []
    if len(df) < _MIN_POINTS:
        problems.append(f"only {len(df)} points (< {_MIN_POINTS}) — refusing a data-starved series")
    if not spec.title:
        problems.append("no title")
    if spec.ylabel.strip().lower() in _PLACEHOLDER_YLABELS:
        problems.append(f"ylabel {spec.ylabel!r} is missing or a placeholder — "
                        f"the reader cannot know what they are looking at")
    if not spec.lines:
        problems.append("no lines to draw")
    if spec.gap and len(spec.lines) != 1:
        problems.append(f"gap mode needs exactly one series, got {len(spec.lines)}")
    return problems


def render_timeseries(df: pd.DataFrame, spec: SeriesSpec, out: str) -> str:
    problems = lint_timeseries(spec, df)
    if problems:
        raise ValueError("CRAFT LINT FAILED — refusing to render:\n  - " + "\n  - ".join(problems))

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#8a8a93", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": "#55555c", "ytick.color": "#55555c",
    })
    fig, ax = plt.subplots(figsize=(13.2, 7.4), dpi=200)
    fig.subplots_adjust(left=0.075, right=0.885, top=0.80, bottom=0.135)
    t = df.index
    handles: list = []

    if spec.gap:
        ln = spec.lines[0]
        v = df[ln.key].to_numpy(dtype=float)
        has_pos, has_neg = bool((v > 0).any()), bool((v < 0).any())
        # A sign earns a legend entry only if it HAS area. fill_between registers a labelled handle
        # even when `where` is all-False, which is how a strictly-positive series (the misery index)
        # came to advertise a "below" swatch for a region that cannot exist.
        ax.fill_between(t, 0, v, where=v >= 0, color=_POS, alpha=0.85, lw=0, zorder=2,
                        interpolate=True)
        ax.fill_between(t, 0, v, where=v < 0, color=_NEG, alpha=0.85, lw=0, zorder=2,
                        interpolate=True)
        ax.plot(t, v, color=INK, lw=1.6, zorder=4, path_effects=_HALO)
        if has_pos and spec.pos_label:
            handles.append(Patch(fc=_POS, alpha=0.85, label=spec.pos_label))
        if has_neg and spec.neg_label:
            handles.append(Patch(fc=_NEG, alpha=0.85, label=spec.neg_label))
    else:
        for ln in spec.lines:
            ax.plot(t, df[ln.key], color=ln.color, lw=2.2, ls=_STYLE.get(ln.style, "-"),
                    zorder=4, path_effects=_HALO)
            handles.append(Line2D([], [], color=ln.color, lw=2.2, ls=_STYLE.get(ln.style, "-"),
                                  label=ln.label))

    if spec.zero_line or spec.gap:
        ax.axhline(0, color="#6b6b73", lw=1.0, zorder=3)
    if spec.hline is not None:
        ax.axhline(spec.hline, color="#6b6b73", lw=1.2, ls=(0, (4, 3)), zorder=3)
        if spec.hline_label:
            handles.append(Line2D([], [], color="#6b6b73", lw=1.2, ls=(0, (4, 3)),
                                  label=spec.hline_label))

    bbox = dict(boxstyle="round,pad=0.35", fc="white", ec="#c8c8d0", lw=0.8, alpha=0.94)
    for co in spec.callouts:
        ax.annotate(co["text"], xy=co["xy"], xytext=co["xytext"], fontsize=9.3, color=INK, bbox=bbox,
                    ha="left", va="center", zorder=8, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color="#9a9aa2", lw=1.0))

    ax.set_xlim(t[0], t[-1])
    ax.yaxis.grid(True, color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylabel(spec.ylabel, fontsize=11.5); ax.set_xlabel(spec.xlabel, fontsize=11.5)
    ax.xaxis.set_major_locator(mdates.YearLocator(spec.tick_years))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(labelsize=10)

    fig.text(0.075, 0.945, spec.title, fontsize=19, fontweight="bold", color=INK)
    fig.text(0.075, 0.885, spec.subtitle, fontsize=11.2, color="#4a4a52", linespacing=1.35)

    if handles:
        leg = ax.legend(handles=handles, loc="best", fontsize=9.8, frameon=True, framealpha=0.92,
                        edgecolor="#d7d7de", handlelength=1.7, labelspacing=0.72, alignment="left")
        leg.get_frame().set_facecolor("white")

    fig.text(0.075, 0.038, spec.source, fontsize=8.2, color="#8a8a93")
    fig.text(0.075, 0.012, spec.footer, fontsize=8.2, color="#8a8a93", style="italic")
    fig.savefig(out, dpi=200, facecolor="white"); plt.close(fig)
    return out


def _tone_color(tone: str | None, i: int) -> str:
    if tone and tone in _TONE:
        return _TONE[tone]
    return _TONE_ORDER[i % len(_TONE_ORDER)]


def _tick_years(df: pd.DataFrame) -> int:
    span = (df.index[-1] - df.index[0]).days / 365.25
    for yrs, step in ((60, 10), (30, 5), (12, 2), (0, 1)):
        if span >= yrs:
            return step
    return 1


def spec_from_run(model: dict, run: dict, chart_id: str,
                  persona_name: str = "") -> tuple[pd.DataFrame, SeriesSpec] | None:
    """Build (df, SeriesSpec) from an authored ``series`` / ``gap_series`` chart + an executed run."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    kind = dc.get("kind")
    if kind not in ("series", "gap_series"):
        return None

    rows: list[dict] = []
    lines: list[Line] = []

    if kind == "series":
        specs = [(s.get("label", ""), _parse_ref(s.get("from", "")), s.get("tone"),
                  s.get("style", "solid")) for s in dc.get("series", [])]
        specs = [x for x in specs if x[1]]
        if not specs:
            return None
        for r in history:
            row = {"date": pd.Timestamp(str(r.as_of)[:10])}
            for lab, rf, _t, _s in specs:
                row[lab] = _value(r, *rf)
            rows.append(row)
        lines = [Line(lab, lab, _tone_color(tone, i), style)
                 for i, (lab, _rf, tone, style) in enumerate(specs)]
        keys = [ln.key for ln in lines]
    else:
        minu, sub = _parse_ref(dc.get("minuend", "")), _parse_ref(dc.get("subtrahend", ""))
        if not minu:
            return None
        label = dc.get("label", "gap")
        for r in history:
            a = _value(r, *minu)
            b = _value(r, *sub) if sub else 0.0
            rows.append({"date": pd.Timestamp(str(r.as_of)[:10]),
                         label: (a - b) if (a is not None and b is not None) else None})
        lines = [Line(label, label, _POS)]
        keys = [label]

    df = pd.DataFrame(rows).set_index("date").dropna(subset=keys)
    if df.empty:
        return None
    df = df.astype(float, errors="ignore")

    # pos_label/neg_label: CHART level first, then data_contract. 14 of 15 catalogs author them at
    # chart level; reading only the contract is what discarded ~20 correct authored labels and left
    # the "above"/"below" defaults that every reviewer flagged as template noise.
    pos = chart.get("pos_label", dc.get("pos_label", "above"))
    neg = chart.get("neg_label", dc.get("neg_label", "below"))

    spec = SeriesSpec(
        title=dc.get("title") or chart_id,
        subtitle=dc.get("subtitle", ""),
        xlabel=dc.get("xlabel", "Year"),
        ylabel=dc.get("ylabel", ""),
        lines=lines,
        source=dc.get("source", f"Model: {model.get('name', model.get('model_id', ''))}. "
                                f"Source: {model.get('source', 'FRED, NY Fed')}."),
        footer=dc.get("footer", "Every value is executed on data — nothing on this chart is authored."),
        tick_years=_tick_years(df),
        zero_line=bool(dc.get("zero_line", False)),
        hline=dc.get("hline"),
        hline_label=dc.get("hline_label", ""),
        gap=(kind == "gap_series" and chart.get("color_job", "diverging") == "diverging"),
        pos_label=pos,
        neg_label=neg,
    )
    return df, spec
