"""Reusable, deterministic chart primitives — verified numbers -> chart.

Each function takes CLEAN, already-computed numbers (a model's verified outputs) plus a matplotlib
axis, and draws one of the catalog's declared `visualizations` forms. No numbers are computed here
and no LLM/diffusion touches a pixel (hard rules #2, #3): rendering is pure deterministic code. The
forms map 1:1 onto the `form`/`color_job`/`dim` a model declares in its visualizations block.
"""
from __future__ import annotations

import numpy as np

from . import theme


def prob_ylim(matrix: np.ndarray, y_levels: np.ndarray, lo_q: float = 0.004, hi_q: float = 0.996):
    """Sensible y-crop for a probability heatmap: the band holding [lo_q, hi_q] of total mass.

    Fixes the prototype flaw where negligible tail mass stretched the axis (0.75%..6.75%) and
    flattened the signal. Returns (ymin, ymax) padded to the level grid.
    """
    mass = matrix.sum(axis=1)
    total = mass.sum()
    if total <= 0:
        return y_levels[0], y_levels[-1]
    cum = np.cumsum(mass) / total
    lo = y_levels[np.searchsorted(cum, lo_q)]
    hi = y_levels[min(np.searchsorted(cum, hi_q), len(y_levels) - 1)]
    pad = (y_levels[1] - y_levels[0]) * 2 if len(y_levels) > 1 else 0.25
    return lo - pad, hi + pad


def fan_chart(ax, x, median, bands, *, mean=None, forward=None, spot=None,
              xticklabels=None, title=None, ylabel="value"):
    """Distribution fan: median line + nested probability bands + optional mean/forward overlays.

    `bands` = list of (lo, hi, label), OUTER band first. color_job = sequential (magnitude of
    confidence). Overlays (mean/forward) are categorical reference lines.
    """
    theme.use_theme()
    seq = theme.SEQUENTIAL
    shades = [seq[1], seq[2], seq[3]]
    for i, (lo, hi, label) in enumerate(bands):
        ax.fill_between(x, lo, hi, color=shades[min(i, len(shades) - 1)],
                        alpha=0.55 - 0.12 * i, linewidth=0, label=label, zorder=2 + i)
    ax.plot(x, median, color=seq[4], lw=2, marker="o", ms=3.5, label="Median", zorder=8)
    if mean is not None:
        ax.plot(x, mean, color=theme.cat(2), lw=2, label="Mean", zorder=9)
    if forward is not None:
        ax.plot(x, forward, color=theme.cat(1), lw=1.8, ls="--", label="Market forward", zorder=10)
    if spot is not None:
        ax.axhline(spot, color=theme.MUTED, lw=1, ls=":", zorder=1)
    if xticklabels is not None:
        ax.set_xticks(list(range(len(xticklabels))))
        ax.set_xticklabels(xticklabels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="y")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)


def probability_heatmap(ax, matrix, xticklabels, y_levels, *, modal=None, mean=None,
                        forward=None, ylim=None, title=None, ylabel="value",
                        cbar_label="probability", fig=None):
    """P(level | time) heatmap (sequential). Overlays: modal / mean / market-forward lines.

    `matrix` shape = (n_levels, n_time). Auto-crops the y-axis via prob_ylim unless `ylim` given.
    """
    theme.use_theme()
    dy = (y_levels[1] - y_levels[0]) / 2 if len(y_levels) > 1 else 0.125
    im = ax.imshow(matrix, aspect="auto", origin="lower", cmap=theme.seq_cmap(), vmin=0,
                   extent=[-0.5, matrix.shape[1] - 0.5, y_levels[0] - dy, y_levels[-1] + dy])
    xs = range(matrix.shape[1])
    if modal is not None:
        ax.plot(xs, modal, color=theme.cat(1), lw=2, marker="o", ms=3.5, label="Modal")
    if mean is not None:
        ax.plot(xs, mean, color=theme.cat(2), lw=2, marker="s", ms=3, label="Mean")
    if forward is not None:
        ax.plot(xs, forward, color=theme.FORWARD, lw=1.6, ls="--", label="Market forward")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(xticklabels, rotation=45, ha="right", fontsize=8)
    ax.set_ylim(*(ylim or prob_ylim(matrix, np.asarray(y_levels))))
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    if any(v is not None for v in (modal, mean, forward)):
        ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    if fig is not None:
        cb = fig.colorbar(im, ax=ax, pad=0.01)
        cb.set_label(cbar_label, fontsize=8)
    return im


def vol_surface_3d(ax3d, moneyness, ttes, Z, *, title=None, zlabel="implied vol (%)"):
    """3D implied-vol surface (moneyness x tenor x vol), sequential by height. NaN holes are masked
    so thin-wing gaps don't spike the surface (the prototype's rough patches)."""
    theme.use_theme()
    X, Y = np.meshgrid(np.asarray(moneyness), np.asarray(ttes))
    Zm = np.ma.masked_invalid(np.asarray(Z))
    surf = ax3d.plot_surface(X, Y, Zm, cmap=theme.seq_cmap(), rstride=1, cstride=1,
                             linewidth=0.15, edgecolor=(0, 0, 0, 0.15), antialiased=True, alpha=0.97)
    ax3d.set_xlabel("moneyness", fontsize=9, labelpad=6)
    ax3d.set_ylabel("time to expiry (yrs)", fontsize=9, labelpad=6)
    ax3d.set_zlabel(zlabel, fontsize=9, labelpad=4)
    ax3d.view_init(elev=26, azim=-58)
    if title:
        ax3d.set_title(title, pad=2)
    return surf


def bar(ax, labels, values, *, color_job="diverging", title=None, ylabel="value", ref=None):
    """Bar/lollipop per category. diverging color_job -> signed coloring (rich/cheap, edge, carry);
    sequential -> single hue. `ref` draws a reference marker line (e.g. an actual/market value)."""
    theme.use_theme()
    vals = np.asarray(values, dtype=float)
    if color_job == "diverging":
        m = np.max(np.abs(vals)) or 1.0
        colors = [theme.div_cmap()(0.5 + 0.5 * v / m) for v in vals]
    else:
        colors = [theme.SEQUENTIAL[3]] * len(vals)
    ax.bar(range(len(vals)), vals, color=colors, width=0.7, zorder=3)
    ax.axhline(0, color=theme.MUTED, lw=1)
    if ref is not None:
        ax.axhline(ref, color=theme.FORWARD, lw=1.6, ls="--", label="reference")
        ax.legend(fontsize=8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="y")


def dumbbell(ax, labels, left, right, *, title=None, xlabel="value",
             left_label="model", right_label="market"):
    """Dumbbell: two values per row (e.g. model fair value vs market), the gap = the trade/edge."""
    theme.use_theme()
    y = range(len(labels))
    for i in y:
        ax.plot([left[i], right[i]], [i, i], color=theme.GRID, lw=2, zorder=1)
    ax.scatter(left, list(y), color=theme.cat(0), s=45, zorder=3, label=left_label)
    ax.scatter(right, list(y), color=theme.cat(1), s=45, zorder=3, label=right_label)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel(xlabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="x")
    ax.legend(fontsize=8, framealpha=0.9)


def overlay_lines(ax, x, series, *, band=None, xticklabels=None, title=None, ylabel="value",
                  zero_line=False):
    """Reusable time-series overlay (categorical identity). `series` = list of (label, y, style)
    where style in {"solid","dashed"}; `band` = (lo, hi, label) shaded region (a gap/premium/spread).

    Serves prescription-vs-actual, implied-vs-realized, divergence-with-threshold, ... — anywhere a
    model's insight is the GAP between two lines over time.
    """
    theme.use_theme()
    if band is not None:
        lo, hi, blabel = band
        ax.fill_between(x, lo, hi, color=theme.SEQUENTIAL[1], alpha=0.5, linewidth=0, label=blabel, zorder=1)
    for i, (label, y, style) in enumerate(series):
        ax.plot(x, y, color=theme.cat(i), lw=2, ls="--" if style == "dashed" else "-",
                marker="o" if style != "dashed" else None, ms=3, label=label, zorder=4 + i)
    if zero_line:
        ax.axhline(0, color=theme.MUTED, lw=1, ls=":")
    if xticklabels is not None:
        step = max(1, len(xticklabels) // 12)
        ax.set_xticks(list(range(0, len(xticklabels), step)))
        ax.set_xticklabels(xticklabels[::step], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="y")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)


def vol_smile(ax, smiles, *, title=None, xlabel="moneyness", ylabel="implied vol (%)"):
    """Vol smiles by expiry (categorical by tenor, sequential-ordered). `smiles` = list of
    (label, moneyness_array, vol_array)."""
    theme.use_theme()
    cmap = theme.seq_cmap()
    n = max(len(smiles), 1)
    for i, (label, m, v) in enumerate(smiles):
        ax.plot(m, v, color=cmap(0.15 + 0.8 * i / n), lw=1.4, label=label)
    ax.axvline(0, color=theme.MUTED, ls=":", lw=1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="both")
    ax.legend(fontsize=6.5, ncol=2, framealpha=0.9)
