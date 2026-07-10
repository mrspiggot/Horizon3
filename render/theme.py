"""Horizon3 rendering theme — color BY JOB (the dataviz discipline).

Charts are Horizon3's differentiator (H2's were the failure). Color is assigned by the job it does,
never by taste: sequential for magnitude/probability, diverging for polarity (two hues + a neutral
gray midpoint), categorical for identity (a fixed order, never cycled). These ramps are the single
place palette choices live; swap them for a brand palette (validate with the dataviz palette script)
and every chart updates.
"""
from __future__ import annotations

import matplotlib as mpl
from matplotlib.colors import LinearSegmentedColormap

# --- ramps (light->dark sequential; two-pole diverging w/ gray mid; fixed categorical order) ---
SEQUENTIAL = ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"]        # single hue
DIVERGING = ["#7f1d1d", "#d6604d", "#f2f2f2", "#4393c3", "#08306b"]         # warm | gray | cool
CATEGORICAL = ["#2171b5", "#e6550d", "#238b45", "#a6559d",
               "#00868b", "#c9a227", "#d6604d", "#6b6ecf"]                  # assign in order

# --- ink / structure tokens (text wears ink, never a series color) ---
INK = "#1a1a1a"
MUTED = "#8a8a8a"
GRID = "#e8e8e8"
FORWARD = "#111111"   # a market/reference overlay line


def seq_cmap() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("h3_seq", SEQUENTIAL)


def div_cmap() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("h3_div", DIVERGING)


def cmap_for(color_job: str) -> LinearSegmentedColormap:
    """The colormap a `color_job` (from a model's visualizations block) maps to."""
    return div_cmap() if color_job == "diverging" else seq_cmap()


def cat(i: int) -> str:
    """i-th categorical hue in fixed order (folds to 'Other' past the list — never generate a hue)."""
    return CATEGORICAL[i % len(CATEGORICAL)]


def style_axes(ax, *, grid_axis: str = "y") -> None:
    """Recessive grid + spines, ink ticks — thin marks, quiet chrome."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=INK, labelsize=8, length=3, width=0.8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def base_rc() -> dict:
    """Matplotlib rc for a clean, consistent figure (white surface; dark mode is a separate step)."""
    return {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelcolor": INK,
        "text.color": INK,
        "axes.edgecolor": MUTED,
    }


def use_theme() -> None:
    mpl.rcParams.update(base_rc())
