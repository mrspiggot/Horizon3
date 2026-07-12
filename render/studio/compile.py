"""Compile a `ChartEncoding` into a deterministic matplotlib figure.

This is the render target of the Chart Studio: the agents reason and emit a `ChartEncoding`
(encoding.py); this module turns it into pixels with code — no diffusion model, every number
from the executed model (CLAUDE.md hard-rule #3). It carries an *editorial* mark vocabulary
(connected scatter, dumbbell, slope, ridgeline, signed area, heatmap) so the grammar can
express the differentiated charts a "muppet with the FT" cannot reproduce.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

from .. import theme  # noqa: E402
from .encoding import ChartEncoding  # noqa: E402


def _df(enc: ChartEncoding) -> pd.DataFrame:
    df = pd.DataFrame(enc.data)
    x = enc.encoding.x
    if x and x.type == "temporal" and x.field in df:
        df[x.field] = pd.to_datetime(df[x.field], errors="coerce")
    return df


def _series_groups(df: pd.DataFrame, enc: ChartEncoding):
    """Split into (label, sub-df) by the identity channel (detail or color); one group if none."""
    key = None
    if enc.encoding.detail:
        key = enc.encoding.detail.field
    elif enc.encoding.color and enc.encoding.color.type in ("nominal", "ordinal"):
        key = enc.encoding.color.field
    if key and key in df:
        return [(str(k), g) for k, g in df.groupby(key, sort=False)]
    lbl = enc.encoding.y.title if (enc.encoding.y and enc.encoding.y.title) else (enc.encoding.y.field if enc.encoding.y else "value")
    return [(lbl, df)]


def _apply_refs_events(ax, enc: ChartEncoding, df: pd.DataFrame):
    # Freeze the data-driven axes so a full-width diagonal/zero line or its shading can't
    # expand them (the classic diagonal-overshoot that wastes half the panel).
    xlim0, ylim0 = ax.get_xlim(), ax.get_ylim()
    for r in enc.annotations.ref_lines:
        if r.orient == "y" and r.value is not None:
            ax.axhline(r.value, ls="--", lw=1.4, color=theme.MUTED, zorder=2)
            if r.label:
                ax.text(0.99, r.value, f" {r.label}", transform=ax.get_yaxis_transform(),
                        color=theme.MUTED, fontsize=8.5, va="bottom", ha="right")
        elif r.orient == "x" and r.value is not None:
            ax.axvline(r.value, ls="--", lw=1.4, color=theme.MUTED, zorder=2)
        elif r.orient == "diagonal" and r.slope is not None:
            b = r.intercept or 0.0
            xs = np.array(xlim0)
            ax.plot(xs, r.slope * xs + b, ls=(0, (6, 4)), lw=1.5, color=theme.MUTED, zorder=2)
            if r.shade_below:
                xf = np.linspace(*xlim0, 60)
                ax.fill_between(xf, ylim0[0], r.slope * xf + b, color=theme.MUTED, alpha=0.06, zorder=1)
            if r.label:
                # place the label where the line is comfortably inside the panel
                lx = xlim0[0] + 0.32 * (xlim0[1] - xlim0[0])
                ax.text(lx, r.slope * lx + b, f"  {r.label}", color=theme.MUTED, fontsize=9,
                        rotation=38, rotation_mode="anchor", va="bottom")
    for e in enc.annotations.events:
        ax.axvline(pd.to_datetime(e.at) if enc.encoding.x and enc.encoding.x.type == "temporal" else float(e.at),
                   color=theme.MUTED, lw=1, ls=":", zorder=2, alpha=0.7)
        ax.annotate(e.label, xy=(pd.to_datetime(e.at) if enc.encoding.x and enc.encoding.x.type == "temporal" else float(e.at), 0.98),
                    xycoords=("data", "axes fraction"), fontsize=8, color=theme.MUTED,
                    rotation=90, va="top", ha="right")
    ax.set_xlim(*xlim0)
    ax.set_ylim(*ylim0)


# ── marks ──────────────────────────────────────────────────────────────────────────────────

def _mark_line_area(ax, enc, df, fill: bool):
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    for i, (lbl, g) in enumerate(_series_groups(df, enc)):
        g = g.sort_values(xf)
        col = theme.cat(i)
        ax.plot(g[xf], g[yf], color=col, lw=2.2, label=lbl, zorder=4, solid_capstyle="round")
        if fill:
            base = 0.0
            ax.fill_between(g[xf], base, g[yf], where=g[yf] >= base, color=col, alpha=0.18, zorder=3)
            if (g[yf] < base).any():
                ax.fill_between(g[xf], base, g[yf], where=g[yf] < base, color=theme.DIVERGING[1], alpha=0.20, zorder=3)
        if enc.annotations.label_last and len(g):
            ax.annotate(f"  {lbl}", (g[xf].iloc[-1], g[yf].iloc[-1]), fontsize=9.5, color=col,
                        fontweight="bold", va="center")


def _mark_connected_scatter(ax, enc, df):
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    tf = None
    # a temporal / ordering field to sequence the path: prefer an explicit 'order' or the color/text time
    for cand in ("order", "date", "t", "time"):
        if cand in df:
            tf = cand
            break
    for i, (lbl, g) in enumerate(_series_groups(df, enc)):
        g = g.sort_values(tf) if tf else g
        X, Y = g[xf].to_numpy(float), g[yf].to_numpy(float)
        col = theme.cat(i)
        n = len(X)
        for k in range(n - 1):
            a = 0.22 + 0.7 * k / max(n - 1, 1)
            ax.plot(X[k:k + 2], Y[k:k + 2], color=col, lw=2.3, alpha=a, solid_capstyle="round", zorder=4)
        for frac in (0.34, 0.62, 0.85):
            k = int(frac * (n - 1))
            if k + 1 < n:
                ax.add_patch(FancyArrowPatch((X[k], Y[k]), (X[k + 1], Y[k + 1]), arrowstyle="-|>",
                             mutation_scale=15, lw=0, color=col, alpha=0.9, zorder=5))
        ax.scatter(X[0], Y[0], s=55, facecolor="white", edgecolor=col, linewidth=2, zorder=6)
        ax.scatter(X[-1], Y[-1], s=140, color=col, edgecolor="white", linewidth=1.5, zorder=7)
        ax.annotate(f"  {lbl}", (X[-1], Y[-1]), fontsize=10.5, fontweight="bold", color=col,
                    va="center", zorder=8)


def _mark_dumbbell(ax, enc, df):
    """Two values per item on one row each — actual vs reference. Needs y=item(nominal),
    and two quantitative fields named by x (start) and text/size (end); we read columns
    'start' and 'end' by convention, falling back to the two quantitative channels."""
    items = df[enc.encoding.y.field].tolist()
    start = df["start"].to_numpy(float) if "start" in df else df[enc.encoding.x.field].to_numpy(float)
    end = df["end"].to_numpy(float) if "end" in df else df[enc.encoding.size.field].to_numpy(float)
    ypos = np.arange(len(items))[::-1]
    for i, y in enumerate(ypos):
        ax.plot([start[i], end[i]], [y, y], color=theme.GRID, lw=3, zorder=2, solid_capstyle="round")
        ax.scatter(start[i], y, s=90, color=theme.cat(0), zorder=4, edgecolor="white", lw=1.2)
        ax.scatter(end[i], y, s=90, color=theme.cat(1), zorder=4, edgecolor="white", lw=1.2)
    ax.set_yticks(ypos)
    ax.set_yticklabels(items)


def _mark_slope(ax, enc, df):
    """Two time points (x has 2 distinct values), one line per item; label ends."""
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    xs = sorted(df[xf].unique())[:2]
    for i, (lbl, g) in enumerate(_series_groups(df, enc)):
        gg = g.set_index(xf)[yf]
        if xs[0] in gg.index and xs[1] in gg.index:
            y0, y1 = float(gg[xs[0]]), float(gg[xs[1]])
            col = theme.cat(i)
            ax.plot([0, 1], [y0, y1], color=col, lw=2, marker="o", ms=5, zorder=4)
            ax.annotate(f"{lbl}  {y1:.2f}", (1, y1), xytext=(6, 0), textcoords="offset points",
                        fontsize=9, color=col, va="center", fontweight="bold")
    ax.set_xticks([0, 1]); ax.set_xticklabels([str(x) for x in xs])
    ax.set_xlim(-0.2, 1.5)


def _mark_bar(ax, enc, df, grouped: bool):
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    cats = df[xf].tolist()
    vals = df[yf].to_numpy(float)
    colors = [theme.DIVERGING[3] if v >= 0 else theme.DIVERGING[1] for v in vals] \
        if enc.color_job == "diverging" else [theme.cat(0)] * len(vals)
    ax.bar(range(len(cats)), vals, color=colors, zorder=3, width=0.68)
    ax.set_xticks(range(len(cats))); ax.set_xticklabels(cats, rotation=30, ha="right")
    ax.axhline(0, color=theme.GRID, lw=0.8)


def _mark_point(ax, enc, df):
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    for i, (lbl, g) in enumerate(_series_groups(df, enc)):
        s = 30
        if enc.encoding.size and enc.encoding.size.field in g:
            sv = g[enc.encoding.size.field].to_numpy(float)
            s = 20 + 260 * (sv - sv.min()) / (np.ptp(sv) or 1)
        ax.scatter(g[xf], g[yf], s=s, color=theme.cat(i), alpha=0.7, edgecolor="white",
                   lw=0.5, label=lbl, zorder=4)


def _mark_heatmap(ax, enc, df, fig):
    """x (temporal/ordinal) × y (nominal rows) → color = quantitative value."""
    xf, yf = enc.encoding.x.field, enc.encoding.y.field
    cf = enc.encoding.color.field
    piv = df.pivot_table(index=yf, columns=xf, values=cf, aggfunc="mean")
    cmap = theme.cmap_for(enc.color_job)
    vmax = np.nanmax(np.abs(piv.values)) if enc.color_job == "diverging" else np.nanmax(piv.values)
    vmin = -vmax if enc.color_job == "diverging" else np.nanmin(piv.values)
    im = ax.imshow(piv.values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax, origin="lower")
    ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index)
    xt = np.linspace(0, piv.shape[1] - 1, min(8, piv.shape[1])).astype(int)
    ax.set_xticks(xt); ax.set_xticklabels([str(piv.columns[i])[:7] for i in xt], rotation=45, ha="right")
    if fig is not None:
        fig.colorbar(im, ax=ax, pad=0.01).set_label(enc.encoding.color.title or cf, fontsize=8)


def _mark_ridgeline(ax, enc, df):
    """Distribution over time: one faint filled density per facet value, vertically offset."""
    ff = enc.encoding.facet.field
    vf = enc.encoding.x.field
    groups = list(df.groupby(ff, sort=True))
    for i, (lbl, g) in enumerate(groups):
        vals = g[vf].to_numpy(float)
        if len(vals) < 3:
            continue
        hist, edges = np.histogram(vals, bins=30, density=True)
        centers = (edges[:-1] + edges[1:]) / 2
        off = i * (hist.max() * 0.6 + 1e-9)
        ax.fill_between(centers, off, off + hist, color=theme.cat(i % 8), alpha=0.55, zorder=i + 2, lw=1)
    ax.set_yticks([i * 1.0 for i in range(len(groups))])
    ax.set_yticklabels([str(l) for l, _ in groups])


_DISPATCH = {
    "line": lambda ax, e, d, f: _mark_line_area(ax, e, d, fill=False),
    "area": lambda ax, e, d, f: _mark_line_area(ax, e, d, fill=True),
    "stacked_area": lambda ax, e, d, f: _mark_line_area(ax, e, d, fill=True),
    "bar": lambda ax, e, d, f: _mark_bar(ax, e, d, grouped=False),
    "grouped_bar": lambda ax, e, d, f: _mark_bar(ax, e, d, grouped=True),
    "connected_scatter": lambda ax, e, d, f: _mark_connected_scatter(ax, e, d),
    "dumbbell": lambda ax, e, d, f: _mark_dumbbell(ax, e, d),
    "slope": lambda ax, e, d, f: _mark_slope(ax, e, d),
    "point": lambda ax, e, d, f: _mark_point(ax, e, d),
    "bubble": lambda ax, e, d, f: _mark_point(ax, e, d),
    "heatmap": lambda ax, e, d, f: _mark_heatmap(ax, e, d, f),
    "ridgeline": lambda ax, e, d, f: _mark_ridgeline(ax, e, d),
}


def compile_encoding(enc: ChartEncoding, out_path: str, *, figsize=(11, 7.2)) -> str:
    """Render a ChartEncoding to `out_path` (PNG). Returns the path."""
    theme.use_theme()
    df = _df(enc)
    fig, ax = plt.subplots(figsize=figsize)
    mark = enc.mark.value if hasattr(enc.mark, "value") else enc.mark
    drawer = _DISPATCH.get(mark)
    if drawer is None:
        raise ValueError(f"compile: unsupported mark '{mark}'")
    drawer(ax, enc, df, fig)

    ex, ey = enc.encoding.x, enc.encoding.y
    if ex and mark not in ("dumbbell", "heatmap", "slope"):
        ax.set_xlabel(ex.title or ex.field, fontsize=11)
    if ey and mark not in ("heatmap", "ridgeline"):
        ax.set_ylabel(ey.title or ey.field, fontsize=11)
    if ey and ey.scale and ey.scale.domain:
        ax.set_ylim(*ey.scale.domain)
    if ex and ex.scale and ex.scale.domain:
        ax.set_xlim(*ex.scale.domain)

    _apply_refs_events(ax, enc, df)

    # legend only when >=2 identity groups and not already direct-labelled to death
    ng = len(_series_groups(df, enc))
    if ng >= 2 and mark in ("line", "area", "point", "bubble") and not enc.annotations.label_last:
        ax.legend(fontsize=9, framealpha=0.9, loc="best")

    ax.set_title(enc.title, fontsize=15, fontweight="bold", loc="left", pad=(20 if enc.subtitle else 8))
    if enc.subtitle:
        ax.text(0, 1.02, enc.subtitle, transform=ax.transAxes, fontsize=10.5, color=theme.MUTED, va="bottom")
    if enc.source_note:
        ax.text(1.0, -0.13, enc.source_note, transform=ax.transAxes, fontsize=7.8, color=theme.MUTED,
                va="top", ha="right")
    theme.style_axes(ax, grid_axis="both")
    fig.savefig(out_path, dpi=145, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
