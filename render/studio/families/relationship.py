"""The RELATIONSHIP structure-family: a model whose output IS the fit between 2+ inputs.

Phillips (unemployment × inflation), Okun (growth × Δunemployment), Beveridge
(unemployment × vacancies): the message is the *shape of the cloud*, not two lines over
time. Two render modes, one lint:

  * ``fit``  — a time-coloured point scatter + an OLS fit line whose slope IS the economic
               coefficient (Okun's ~−0.4; Phillips' ~0 = Friedman vertical),
  * ``path`` — a time-coloured connected trajectory (Beveridge's post-2020 shift),

both with axes that carry units and a labelled time ramp. ``lint_relationship`` REFUSES to
emit a chart with an unlabelled/unitless axis, a missing time legend, or bare dots (no fit
and no path) — precisely the defects that shipped once and must never ship again.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib import patheffects as pe

from ..from_model import _label, _parse_ref, _value

INK, GRID = "#16161d", "#d7d7de"
_HALO = [pe.Stroke(linewidth=3.2, foreground="white"), pe.Normal()]
_UNIT_HINTS = ("%", "pp", "bp", "index", "$", "ratio", "σ", "z-", "prob")
_CMAP = "cividis"   # perceptually uniform + colourblind-safe time ramp


@dataclass
class RelationshipSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str
    x_key: str
    y_key: str
    mode: str                      # "fit" | "path"
    cbar_label: str
    source: str
    footer: str
    annotations: list[dict] = field(default_factory=list)


def _units_ok(lbl: str) -> bool:
    return any(u in lbl for u in _UNIT_HINTS)


def lint_relationship(spec: RelationshipSpec, df: pd.DataFrame) -> list[str]:
    p = []
    if not spec.xlabel.strip():
        p.append("x-axis label is empty")
    elif not _units_ok(spec.xlabel):
        p.append(f"x-axis label states no unit: {spec.xlabel!r}")
    if not spec.ylabel.strip():
        p.append("y-axis label is empty")
    elif not _units_ok(spec.ylabel):
        p.append(f"y-axis label states no unit: {spec.ylabel!r}")
    if spec.mode not in ("fit", "path"):
        p.append("mode must be 'fit' or 'path' — bare dots (neither) are forbidden")
    if spec.x_key not in df.columns or spec.y_key not in df.columns:
        p.append("x/y column missing from data")
    elif len(df.dropna(subset=[spec.x_key, spec.y_key])) < 10:
        p.append("fewer than 10 valid (x, y) points — not a relationship")
    if not spec.cbar_label.strip():
        p.append("time ramp has no label")
    return p


def render_relationship(df: pd.DataFrame, spec: RelationshipSpec, out: str) -> str:
    problems = lint_relationship(spec, df)
    if problems:
        raise ValueError("CRAFT LINT FAILED — refusing to render:\n  - " + "\n  - ".join(problems))

    d = df.dropna(subset=[spec.x_key, spec.y_key]).reset_index(drop=True)
    x = d[spec.x_key].to_numpy(dtype=float)
    y = d[spec.y_key].to_numpy(dtype=float)
    order = np.arange(len(d))
    years = pd.to_datetime(d["date"]).dt.year.to_numpy() if "date" in d else order

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#8a8a93", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": "#55555c", "ytick.color": "#55555c",
    })
    fig, ax = plt.subplots(figsize=(11.6, 7.8), dpi=200)
    fig.subplots_adjust(left=0.085, right=0.86, top=0.80, bottom=0.11)

    if spec.mode == "path":
        pts = np.column_stack([x, y]).reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(segs, cmap=_CMAP, zorder=2, lw=2.0, alpha=0.9)
        lc.set_array(order[:-1]); ax.add_collection(lc)
        sc = ax.scatter(x, y, c=order, cmap=_CMAP, s=26, zorder=3, edgecolor="white", linewidth=0.4)
    else:  # fit
        sc = ax.scatter(x, y, c=order, cmap=_CMAP, s=34, zorder=3, edgecolor="white", linewidth=0.4)
        b1, b0 = np.polyfit(x, y, 1)
        r = np.corrcoef(x, y)[0, 1]
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, b0 + b1 * xs, color=INK, lw=2.2, zorder=4, path_effects=_HALO)
        flat = (r**2 < 0.10) or (abs(b1) < 0.08)   # weak fit ⇒ no stable relationship
        note = (f"OLS slope = {b1:+.2f}   R² = {r**2:.2f}\n"
                + ("≈ flat — no stable relationship" if flat else "the slope IS the economic coefficient"))
        ax.annotate(note, xy=(0.03, 0.045), xycoords="axes fraction", fontsize=9.8, color=INK,
                    ha="left", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#c8c8d0", lw=0.8, alpha=0.95))

    # emphasise + label the latest observation (offset clear of the fit line)
    ax.scatter([x[-1]], [y[-1]], s=150, facecolor="none", edgecolor=INK, linewidth=2.0, zorder=6)
    last_date = str(pd.to_datetime(d["date"].iloc[-1]).date()) if "date" in d else "latest"
    xname = spec.xlabel.split("(")[0].split(",")[0].strip()
    yname = spec.ylabel.split("(")[0].split(",")[0].strip()
    ax.annotate(f"latest ({last_date[:7]}):  {xname} {x[-1]:.1f},  {yname} {y[-1]:.1f}",
                xy=(x[-1], y[-1]), xytext=(14, -30), textcoords="offset points", fontsize=9.2,
                color=INK, va="top", ha="left", zorder=7,
                arrowprops=dict(arrowstyle="-", color="#9a9aa2", lw=0.9),
                path_effects=[pe.Stroke(linewidth=2.4, foreground="white"), pe.Normal()])

    for an in spec.annotations:
        ax.annotate(an["text"], xy=an["xy"], xytext=an["xytext"], fontsize=9.2, color=INK,
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#c8c8d0", lw=0.8, alpha=0.94),
                    ha="left", va="center", zorder=8, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color="#9a9aa2", lw=1.0))

    ax.grid(True, color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel(spec.xlabel, fontsize=11.5); ax.set_ylabel(spec.ylabel, fontsize=11.5)
    ax.tick_params(labelsize=10)
    ax.margins(0.06)

    cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.045)
    if len(years) > 1:
        cbar.set_ticks([order[0], order[len(order) // 2], order[-1]])
        cbar.set_ticklabels([str(years[0]), str(years[len(years) // 2]), str(years[-1])])
    cbar.set_label(spec.cbar_label, fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    fig.text(0.085, 0.945, spec.title, fontsize=18, fontweight="bold", color=INK)
    sub = "\n".join(textwrap.wrap(spec.subtitle.replace("→", "–"), width=104)[:2])
    fig.text(0.085, 0.875, sub, fontsize=10.8, color="#4a4a52", linespacing=1.32, va="top")
    fig.text(0.085, 0.028, spec.source, fontsize=8.2, color="#8a8a93")
    fig.text(0.085, 0.006, spec.footer, fontsize=8.2, color="#8a8a93", style="italic")
    fig.savefig(out, dpi=200, facecolor="white"); plt.close(fig)
    return out


def spec_from_run(model: dict, run: dict, chart_id: str, persona_name: str = "") \
        -> tuple[pd.DataFrame, RelationshipSpec] | None:
    """Build (df, RelationshipSpec) from an authored kind:scatter/pearson chart + executed run."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    if dc.get("kind") not in ("scatter", "pearson"):
        return None
    xr, yr = _parse_ref(dc.get("x", "")), _parse_ref(dc.get("y", ""))
    if not xr or not yr:
        return None
    xcol, ycol = _label(xr[1], xr[2]), _label(yr[1], yr[2])
    rows = []
    for i, r in enumerate(history):
        xv, yv = _value(r, *xr), _value(r, *yr)
        if xv is not None and yv is not None:
            rows.append({xcol: float(xv), ycol: float(yv), "order": i, "date": str(r.as_of)[:10]})
    if len(rows) < 10:
        return None
    df = pd.DataFrame(rows)
    yrs = pd.to_datetime(df["date"]).dt.year
    mode = "path" if dc.get("path") else "fit"
    insight = " ".join((chart.get("insight") or "").split())
    subtitle = insight if len(insight) <= 200 else insight[:197] + "…"
    spec = RelationshipSpec(
        title=dc.get("title") or chart_id,
        subtitle=dc.get("subtitle") or subtitle,
        xlabel=dc.get("xlabel", xcol), ylabel=dc.get("ylabel", ycol),
        x_key=xcol, y_key=ycol, mode=mode,
        cbar_label=f"observation year  ({yrs.min()}–{yrs.max()})",
        source=dc.get("source", f"Model: {model.get('name', model.get('model_id', ''))}. "
                                f"Source: {', '.join(sorted({i.get('db_source','') for i in model.get('inputs', []) if i.get('db_source')}))}."),
        footer="Every value is executed on data — nothing on this chart is authored by the model.",
    )
    return df, spec
