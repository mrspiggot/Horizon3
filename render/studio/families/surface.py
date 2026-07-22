"""The SURFACE structure-family: one quantity read across an ordered dimension over time.

A term-premium surface (tenor × time), a vol surface, a credit-quality ladder, a
financial-conditions panel, a commodity-momentum grid — all the same shape: an ORDERED
set of items, each a series through time, where the value is a colour. The canonical form
is a heatmap (never a tangle of lines): diverging colour around zero when the value is
signed, sequential when it is one-signed.

One lint refuses an unlabelled colour ramp (a heatmap with no legend is unreadable), a
missing unit, or fewer than two items (that is just a line).
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from ..from_model import _parse_ref, _value

INK = "#16161d"
_UNIT_HINTS = ("%", "pp", "bp", "index", "$", "ratio", "σ", "sigma", "z-", "return", "vol")


@dataclass
class SurfaceSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str            # the item-axis label (e.g. "tenor", "quality", "commodity")
    cbar_label: str
    items: list[str]       # ordered item labels (bottom→top as authored is top→bottom)
    signed: bool
    source: str
    footer: str


def lint_surface(spec: SurfaceSpec, mat: np.ndarray) -> list[str]:
    p = []
    if not spec.cbar_label.strip():
        p.append("colour ramp has no label — a heatmap with no legend is unreadable")
    elif not any(u in spec.cbar_label.lower() for u in _UNIT_HINTS):
        p.append(f"colour ramp states no unit: {spec.cbar_label!r}")
    if not spec.xlabel.strip():
        p.append("x-axis label is empty")
    if len(spec.items) < 2:
        p.append("a surface needs ≥2 items (else it is a single series)")
    if mat.size == 0 or np.isnan(mat).all():
        p.append("the item × time matrix is empty")
    return p


def render_surface(dates: list, mat: np.ndarray, spec: SurfaceSpec, out: str) -> str:
    """mat: shape (n_items, n_dates), row 0 = spec.items[0] (drawn at TOP)."""
    problems = lint_surface(spec, mat)
    if problems:
        raise ValueError("CRAFT LINT FAILED — refusing to render:\n  - " + "\n  - ".join(problems))

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#8a8a93", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": "#55555c", "ytick.color": "#55555c",
    })
    fig, ax = plt.subplots(figsize=(12.6, 5.6 + 0.3 * len(spec.items)), dpi=200)
    # leave room on the right for the colour bar AND its rotated label (right=0.995 clipped it)
    fig.subplots_adjust(left=0.10, right=0.90, top=0.80, bottom=0.13)

    x = mdates.date2num(pd.to_datetime(dates).to_pydatetime())
    # cell edges (midpoints; extrapolate ends) so pcolormesh aligns cells to dates
    xe = np.concatenate([[x[0] - (x[1] - x[0]) / 2],
                         (x[:-1] + x[1:]) / 2,
                         [x[-1] + (x[-1] - x[-2]) / 2]])
    ye = np.arange(len(spec.items) + 1)

    finite = mat[np.isfinite(mat)]
    vmin_u = vmax_u = None
    if spec.signed:
        # anchor the diverging scale at the 95th percentile of |value|, not the max — one outlier
        # stretching vmin/vmax to ±max washes the whole heatmap out to near-white (the review's
        # "washed-out surface"). The bulk now fills the colormap; genuine extremes saturate the ends.
        m = float(np.nanpercentile(np.abs(finite), 95)) or float(np.nanmax(np.abs(finite))) or 1.0
        norm, cmap = TwoSlopeNorm(vcenter=0.0, vmin=-m, vmax=m), "RdBu_r"
    else:
        # SAME wash-out on the UNSIGNED branch (the vol implied-vol surface, 6 rounds): a COVID vol
        # spike pins vmax near 80 and the recent 12-20 range collapses into one dark band. Anchor on the
        # robust 2nd-98th percentile so the bulk fills cividis; the spike still saturates the top.
        vmin_u, vmax_u = float(np.nanpercentile(finite, 2)), float(np.nanpercentile(finite, 98))
        if vmax_u <= vmin_u:
            vmin_u, vmax_u = float(np.nanmin(finite)), float(np.nanmax(finite))
        norm, cmap = None, "cividis"
    # draw with items[0] at the TOP: reverse rows so top row is last in y
    mesh = ax.pcolormesh(xe, ye, mat[::-1], cmap=cmap, norm=norm,
                         vmin=vmin_u, vmax=vmax_u, shading="flat")
    mesh.set_edgecolor("face")

    ax.set_yticks(np.arange(len(spec.items)) + 0.5)
    ax.set_yticklabels(list(reversed(spec.items)), fontsize=10.5)
    ax.set_ylabel(spec.ylabel, fontsize=11.5)
    ax.set_xlabel(spec.xlabel, fontsize=11.5)
    ax.xaxis_date()
    span_days = x[-1] - x[0]
    loc = mdates.YearLocator(2 if span_days > 365 * 12 else 1) if span_days > 400 else mdates.MonthLocator(interval=2)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if span_days > 400 else "%b %Y"))
    ax.tick_params(labelsize=10)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)

    cbar = fig.colorbar(mesh, ax=ax, pad=0.015, fraction=0.045)
    cbar.set_label(spec.cbar_label, fontsize=10.5)
    cbar.ax.tick_params(labelsize=9)

    fig.text(0.10, 0.945, spec.title, fontsize=18, fontweight="bold", color=INK)
    # the RENDERER, not the authored text, chooses the colormap — strip any colour-word claims
    # (e.g. "tightened (blue)") that could contradict it; the labelled colour bar states the mapping.
    clean = re.sub(r"\s*\((?:blue|red|amber|green|grey|gray|yellow|orange)\)", "",
                   spec.subtitle, flags=re.IGNORECASE).replace("→", "–")
    sub = "\n".join(textwrap.wrap(clean, width=110))   # full subtitle, never drop lines
    fig.text(0.10, 0.875, sub, fontsize=10.8, color="#4a4a52", linespacing=1.32, va="top")
    fig.text(0.10, 0.035, spec.source, fontsize=8.2, color="#8a8a93")
    fig.text(0.10, 0.012, spec.footer, fontsize=8.2, color="#8a8a93", style="italic")
    # bbox_inches="tight" guarantees the colour-key on the right is never clipped
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    return out


def spec_from_run(model: dict, run: dict, chart_id: str, persona_name: str = ""):
    """Build (dates, matrix, SurfaceSpec) from an authored kind:heatmap chart + executed run."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    if dc.get("kind") != "heatmap":
        return None
    items = [(r.get("label"), _parse_ref(r.get("from", ""))) for r in (dc.get("rows") or [])]
    items = [(lab, ref) for lab, ref in items if lab and ref]
    if len(items) < 2:
        return None

    dates, cols = [], []
    for r in history:
        col = [(_value(r, *ref) if ref else None) for _lab, ref in items]
        if any(v is not None for v in col):
            dates.append(pd.Timestamp(str(r.as_of)[:10]))
            cols.append([np.nan if v is None else float(v) for v in col])
    if len(dates) < 3:
        return None
    mat = np.array(cols).T   # (n_items, n_dates)
    # authored `diverging` wins; else auto-detect from the data's sign
    if "diverging" in dc:
        signed = bool(dc["diverging"])
    else:
        signed = bool(np.nanmin(mat) < -1e-9)

    insight = " ".join((chart.get("insight") or "").split())
    spec = SurfaceSpec(
        title=dc.get("title") or chart_id,
        subtitle=dc.get("subtitle") or insight,
        xlabel="Year" if (dates[-1] - dates[0]).days > 400 else "date",
        ylabel=dc.get("ylabel_items") or dc.get("item_axis") or "",
        cbar_label=dc.get("cbar_label") or dc.get("ylabel") or "value",
        items=[lab for lab, _ in items], signed=signed,
        source=dc.get("source", f"Model: {model.get('name', model.get('model_id',''))}. "
                                f"Source: {', '.join(sorted({i.get('db_source','') for i in model.get('inputs', []) if i.get('db_source')}))}."),
        footer="Every value is executed on data — nothing on this chart is authored by the model.")
    return dates, mat, spec
