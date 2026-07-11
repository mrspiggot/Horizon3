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


def scatter(ax, x, y, labels=None, *, ref_line=False, ref_label="fair (45°)",
            title=None, xlabel="x", ylabel="y", color_job="categorical"):
    """Scatter with optional 45° reference line + direct point labels. The DISTANCE from the ref line
    is the signal (earnings yield vs bond yield, model vs market). color_job diverging/sequential
    colors points by their y (polarity/magnitude); categorical = one identity hue."""
    theme.use_theme()
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if color_job in ("sequential", "diverging"):
        cmap = theme.cmap_for(color_job)
        if color_job == "diverging":
            m = np.max(np.abs(y)) or 1.0
            cols = [cmap(0.5 + 0.5 * v / m) for v in y]
        else:
            lo, hi = float(np.min(y)), float(np.max(y))
            rng = (hi - lo) or 1.0
            cols = [cmap(0.15 + 0.78 * (v - lo) / rng) for v in y]
    else:
        cols = theme.cat(0)
    if ref_line:
        lo = float(min(x.min(), y.min()))
        hi = float(max(x.max(), y.max()))
        pad = (hi - lo) * 0.06 or 1.0
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=theme.MUTED, ls="--",
                lw=1.2, zorder=1, label=ref_label)
    ax.scatter(x, y, c=cols, s=64, zorder=3, edgecolors="white", linewidths=0.8)
    if labels is not None:
        for xi, yi, lab in zip(x, y, labels):
            ax.annotate(str(lab), (xi, yi), textcoords="offset points", xytext=(5, 4),
                        fontsize=8, color=theme.INK)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="both")
    if ref_line:
        ax.legend(fontsize=8, framealpha=0.9)


def stacked_area(ax, x, layers, *, xticklabels=None, title=None, ylabel="value", total_label=None):
    """Stacked composition over x: `layers` = list of (label, y_array), summed to show the total and
    which component drives it (funding = risk-free + OAS; attribution over time). A 2px white surface
    gap between fills (the dataviz spacer rule)."""
    theme.use_theme()
    labels = [lab for lab, _ in layers]
    ys = [np.asarray(y, dtype=float) for _, y in layers]
    cols = [theme.cat(i) for i in range(len(ys))]
    ax.stackplot(x, *ys, labels=labels, colors=cols, alpha=0.9, edgecolor="white", linewidth=2)
    if total_label:
        total = np.sum(ys, axis=0)
        ax.plot(x, total, color=theme.FORWARD, lw=1.8, label=total_label, zorder=5)
    if xticklabels is not None:
        step = max(1, len(xticklabels) // 12)
        ax.set_xticks(list(range(0, len(xticklabels), step)))
        ax.set_xticklabels(xticklabels[::step], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    theme.style_axes(ax, grid_axis="y")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)


def color_table(ax, columns, row_labels, values, *, color_job="sequential", title=None,
                fmt="{:.2f}", normalize="column"):
    """Color-coded tabular: a value matrix (`values`[row][col]) with each cell shaded by job —
    sequential = magnitude, diverging = polarity around 0. `normalize` = "column" (each metric shows
    its own gradient — the right default for a multi-metric league table) or "table" (one shared
    scale). Header/row-label cells wear the ink token; data-cell text flips to white on dark
    backgrounds for contrast. The 'information-rich table' form."""
    theme.use_theme()
    ax.axis("off")
    vals = np.asarray(values, dtype=float)
    cmap = theme.cmap_for(color_job)
    n_rows, n_cols = len(row_labels), len(columns)

    # per-scope reference (whole table, or per column) for normalization
    if normalize == "column":
        scope = [vals[:, c] for c in range(n_cols)]
    else:
        scope = [vals.ravel()] * n_cols

    def _cellcol(v, c):
        col_vals = scope[c]
        if color_job == "diverging":
            m = np.nanmax(np.abs(col_vals)) or 1.0
            return cmap(0.5 + 0.5 * v / m)
        lo, hi = float(np.nanmin(col_vals)), float(np.nanmax(col_vals))
        rng = (hi - lo) or 1.0
        return cmap(0.12 + 0.78 * (v - lo) / rng)

    tbl = ax.table(
        cellText=[[fmt.format(vals[r][c]) for c in range(n_cols)] for r in range(n_rows)],
        rowLabels=row_labels, colLabels=columns, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.5)
    for (r, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_linewidth(2)  # 2px surface gap between cells
        if r == 0 or col == -1:  # header row / row-label column
            cell.set_facecolor("#f2f2f2")
            cell.get_text().set_color(theme.INK)
            cell.get_text().set_weight("bold")
        else:
            bg = _cellcol(vals[r - 1][col], col)
            cell.set_facecolor(bg)
            lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
            cell.get_text().set_color("white" if lum < 0.5 else theme.INK)
    if title:
        ax.set_title(title, pad=14)
