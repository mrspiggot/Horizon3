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
        # A CONTINUOUS TIME RAMP or high-cardinality field is an ENCODING, not an identity to split
        # on. Grouping it makes every point its own "series" and labels each — the Beveridge locus
        # shipped ~300 index labels ("231, 254, …") over an unreadable cluster. Treat as one series.
        if key not in ("order", "date", "t", "time", "index") and df[key].nunique() <= 12:
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
                # anchor the label at ~40% panel HEIGHT on the line, so it never rides up into
                # the title/subtitle band (the collision the visual critic flagged); fall back
                # along x if that point is off-panel.
                y_t = ylim0[0] + 0.40 * (ylim0[1] - ylim0[0])
                lx = (y_t - b) / r.slope if r.slope else xlim0[0]
                if not (xlim0[0] < lx < xlim0[1]):
                    lx = xlim0[0] + 0.22 * (xlim0[1] - xlim0[0])
                ax.text(lx, r.slope * lx + b, f"  {r.label}", color=theme.MUTED, fontsize=9,
                        rotation=38, rotation_mode="anchor", va="bottom")
    x_is_temporal = bool(enc.encoding.x and enc.encoding.x.type == "temporal")
    for e in enc.annotations.events:
        # An event only lands on a temporal x-axis. If the agent anchored a date to a
        # non-temporal axis (e.g. a connected scatter over inflation), skip it rather than
        # crash — the visual critic will note anything genuinely missing.
        try:
            xv = pd.to_datetime(e.at) if x_is_temporal else float(e.at)
        except (ValueError, TypeError):
            continue
        ax.axvline(xv, color=theme.MUTED, lw=1, ls=":", zorder=2, alpha=0.7)
        ax.annotate(e.label, xy=(xv, 0.98), xycoords=("data", "axes fraction"), fontsize=8,
                    color=theme.MUTED, rotation=90, va="top", ha="right")
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
        # label the endpoint with WHERE-IN-TIME the path ends, not the y-axis title (which is redundant
        # with the axis — the v6 Beveridge locus ended in a bare "Job vacancy rate (%)"). Keep a real
        # series identity when there is one (multi-group paths).
        ytitle = (enc.encoding.y.title or "").strip().lower()
        end = lbl if (lbl and lbl.strip().lower() != ytitle) else ""
        if not end and tf in ("date", "t", "time"):
            try:
                end = pd.to_datetime(g[tf].iloc[-1]).strftime("%b %Y")
            except Exception:
                end = "latest"
        ax.annotate(f"  {end or 'latest'}", (X[-1], Y[-1]), fontsize=10.5, fontweight="bold", color=col,
                    va="center", zorder=8)


def _mark_dumbbell(ax, enc, df):
    """Long-form: y=item (nominal), x=value (quantitative), color/detail=phase (2 categories,
    e.g. actual vs rule). One horizontal connector per item joins its two phase points — the
    gap (divergence) reads at a glance. Grammar-consistent: no special columns."""
    itemf = enc.encoding.y.field
    valf = enc.encoding.x.field
    phasef = (enc.encoding.color.field if enc.encoding.color
              else (enc.encoding.detail.field if enc.encoding.detail else None))
    items = list(dict.fromkeys(df[itemf]))
    phases = list(dict.fromkeys(df[phasef])) if phasef and phasef in df else []
    ypos = {it: len(items) - 1 - i for i, it in enumerate(items)}
    for it in items:
        sub = df[df[itemf] == it]
        xs = sub[valf].astype(float).tolist()
        y = ypos[it]
        if len(xs) >= 2:
            ax.plot([min(xs), max(xs)], [y, y], color=theme.GRID, lw=3.5, zorder=2, solid_capstyle="round")
        for _, row in sub.iterrows():
            ci = phases.index(row[phasef]) if phasef else 0
            ax.scatter(float(row[valf]), y, s=110, color=theme.cat(ci), zorder=4, edgecolor="white", lw=1.3)
    ax.set_yticks(list(ypos.values()))
    ax.set_yticklabels(list(ypos.keys()))
    for i, p in enumerate(phases):
        ax.scatter([], [], color=theme.cat(i), label=str(p))
    if phases:
        ax.legend(fontsize=9, loc="best", framealpha=0.9)


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
    gf = (enc.encoding.color.field if enc.encoding.color else
          (enc.encoding.detail.field if enc.encoding.detail else None))
    if grouped and gf and gf in df and gf != xf:
        # real grouped bars: one cluster per x category, a bar per group value
        cats = list(dict.fromkeys(df[xf]))
        groups = list(dict.fromkeys(df[gf]))
        xi = np.arange(len(cats)); w = 0.8 / max(len(groups), 1)
        for j, gval in enumerate(groups):
            sub = df[df[gf] == gval].set_index(xf)[yf]
            ys = [float(sub.get(c, np.nan)) for c in cats]
            ax.bar(xi + (j - (len(groups) - 1) / 2) * w, ys, width=w, color=theme.cat(j),
                   label=str(gval), zorder=3)
        ax.set_xticks(xi); ax.set_xticklabels(cats, rotation=30, ha="right")
        ax.axhline(0, color=theme.GRID, lw=0.8)
        ax.legend(fontsize=9, framealpha=0.9)
        return
    cats = df[xf].tolist()
    vals = df[yf].to_numpy(float)
    colors = [theme.DIVERGING[3] if v >= 0 else theme.DIVERGING[1] for v in vals] \
        if enc.color_job == "diverging" else [theme.cat(0)] * len(vals)
    ax.bar(range(len(cats)), vals, color=colors, zorder=3, width=0.68)
    ax.set_xticks(range(len(cats))); ax.set_xticklabels(cats, rotation=30, ha="right")
    ax.axhline(0, color=theme.GRID, lw=0.8)


def _mark_waterfall(ax, enc, df):
    """A decomposition built up step by step: each component bar starts where the last ended;
    a final 'total' bar closes to the cumulative sum. Uses the latest snapshot per component."""
    compf = (enc.encoding.color.field if enc.encoding.color else
             (enc.encoding.detail.field if enc.encoding.detail else enc.encoding.x.field))
    valf = enc.encoding.y.field if enc.encoding.y else "value"
    if "date" in df:  # take the latest snapshot of each component
        last = df["date"].max()
        snap = df[df["date"] == last]
    else:
        snap = df
    comps = list(dict.fromkeys(snap[compf]))
    vals = [float(snap[snap[compf] == c][valf].iloc[-1]) for c in comps]
    cum = 0.0
    for i, (c, v) in enumerate(zip(comps, vals)):
        col = theme.DIVERGING[3] if v >= 0 else theme.DIVERGING[1]
        ax.bar(i, v, bottom=cum, color=col, zorder=3, width=0.66)
        cum += v
    ax.bar(len(comps), cum, color=theme.INK, alpha=0.85, zorder=3, width=0.66)
    ax.set_xticks(range(len(comps) + 1))
    ax.set_xticklabels([str(c) for c in comps] + ["total"], rotation=30, ha="right")
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


def _drop_total_from_stack(piv):
    """NUMERIC SANITY (rule #2 at the chart layer): if one column IS the sum of the others, it is the
    TOTAL mistakenly included as a stackable band — stacking it on its own components DOUBLES the
    reading (the GZ spread shipped at ~16pp vs a true ~8). Drop it; the cumulative line draws the total."""
    cols = list(piv.columns)
    if len(cols) < 3:
        return piv
    for c in cols:
        others = piv[[x for x in cols if x != c]].sum(axis=1)
        scale = float(others.abs().mean()) + 1e-9
        if float((piv[c].fillna(0) - others.fillna(0)).abs().mean()) < 0.05 * scale:
            import sys as _sys
            print(f"CHART SANITY — dropped total-among-components {c!r} from the stack (it equals the "
                  f"sum of the others; stacking it would double-count)", file=_sys.stderr)
            return piv.drop(columns=[c])
    return piv


def _mark_stacked(ax, enc, df):
    """True part-to-whole over time: cumulatively stack the components so they SUM to the total,
    with a total line on top. Handles signed components (a negative component dips the stack
    below the one beneath it). Base = the larger/steadier component (highest mean), so the
    volatile residual reads on top."""
    xf = enc.encoding.x.field
    yf = enc.encoding.y.field
    catf = (enc.encoding.color.field if enc.encoding.color
            else (enc.encoding.detail.field if enc.encoding.detail else None))
    if not catf or catf not in df:
        return _mark_line_area(ax, enc, df, fill=True)
    piv = df.pivot_table(index=xf, columns=catf, values=yf, aggfunc="sum").sort_index()
    piv = _drop_total_from_stack(piv)                          # rule #2 at the chart layer (below)
    order = piv.mean().sort_values(ascending=False).index      # steadiest/largest as the base
    piv = piv[order]
    x = pd.to_datetime(piv.index) if (enc.encoding.x and enc.encoding.x.type == "temporal") else piv.index
    cum = np.zeros(len(piv))
    for i, comp in enumerate(piv.columns):
        vals = piv[comp].fillna(0).to_numpy(float)
        ax.fill_between(x, cum, cum + vals, color=theme.cat(i), alpha=0.6, lw=0.4,
                        label=str(comp), zorder=3 + i)
        cum = cum + vals
    ax.plot(x, cum, color=theme.INK, lw=1.6, label="total", zorder=10)
    ax.axhline(0, color=theme.GRID, lw=0.8, zorder=2)
    ax.legend(fontsize=9, framealpha=0.9, loc="upper left")


def _mark_ridgeline(ax, enc, df):
    """Distribution over a grouping: one faint filled density per group value, vertically offset."""
    ff = (enc.encoding.facet.field if enc.encoding.facet else
          (enc.encoding.detail.field if enc.encoding.detail else
           (enc.encoding.color.field if enc.encoding.color else None)))
    vf = enc.encoding.x.field
    if not ff or ff not in df:
        # single distribution — one ridge
        vals = df[vf].to_numpy(float)
        if len(vals) >= 3:
            hist, edges = np.histogram(vals, bins=30, density=True)
            centers = (edges[:-1] + edges[1:]) / 2
            ax.fill_between(centers, 0, hist, color=theme.cat(0), alpha=0.55, lw=1)
        return
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
    "stacked_area": lambda ax, e, d, f: _mark_stacked(ax, e, d),
    "bar": lambda ax, e, d, f: _mark_bar(ax, e, d, grouped=False),
    "grouped_bar": lambda ax, e, d, f: _mark_bar(ax, e, d, grouped=True),
    "connected_scatter": lambda ax, e, d, f: _mark_connected_scatter(ax, e, d),
    "dumbbell": lambda ax, e, d, f: _mark_dumbbell(ax, e, d),
    "slope": lambda ax, e, d, f: _mark_slope(ax, e, d),
    "point": lambda ax, e, d, f: _mark_point(ax, e, d),
    "bubble": lambda ax, e, d, f: _mark_point(ax, e, d),
    "heatmap": lambda ax, e, d, f: _mark_heatmap(ax, e, d, f),
    "ridgeline": lambda ax, e, d, f: _mark_ridgeline(ax, e, d),
    "waterfall": lambda ax, e, d, f: _mark_waterfall(ax, e, d),
}


def _cap(s: str | None, n: int) -> str | None:
    """Cap text — an over-long unwrapped title/subtitle/note blows the tight bbox to an impossible size."""
    if not s:
        return s
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _coerce_domain(ch, dom):
    if ch and ch.type == "temporal":
        return [pd.to_datetime(v) for v in dom]
    try:
        return [float(v) for v in dom]
    except (TypeError, ValueError):
        return None


def _draw_on_axes(ax, enc: ChartEncoding, df, fig, mark: str, *, panel: bool = False):
    """Draw the mark + refs + domain + legend on one Axes. `panel=True` for a small-multiple cell
    (suppresses per-panel axis labels; the figure carries shared labels)."""
    _DISPATCH[mark](ax, enc, df, fig)
    ex, ey = enc.encoding.x, enc.encoding.y
    if not panel:
        if ex and mark not in ("dumbbell", "heatmap", "slope"):
            ax.set_xlabel(ex.title or ex.field, fontsize=11)
        if ey and mark not in ("heatmap", "ridgeline"):
            ax.set_ylabel(ey.title or ey.field, fontsize=11)
    if ey and ey.scale and ey.scale.domain:
        d = _coerce_domain(ey, ey.scale.domain)
        if d:
            ax.set_ylim(*d)
    if ex and ex.scale and ex.scale.domain and mark not in ("dumbbell", "heatmap", "slope"):
        d = _coerce_domain(ex, ex.scale.domain)
        if d:
            ax.set_xlim(*d)
    _apply_refs_events(ax, enc, df)
    ng = len(_series_groups(df, enc))
    if ng >= 2 and mark in ("line", "area", "point", "bubble") and not enc.annotations.label_last and not panel:
        ax.legend(fontsize=9, framealpha=0.9, loc="best")
    theme.style_axes(ax, grid_axis="both")


def _savefig(fig, out_path, *, tight: bool = True):
    # tight-bbox expands the canvas to fit stray artists (e.g. a connected-scatter's endpoint labels
    # in a small panel) — fine for a single axes, catastrophic for a faceted grid (17k-px strips).
    # Faceted figures use their computed size and CLIP overflow instead.
    if tight:
        try:
            fig.savefig(out_path, dpi=145, bbox_inches="tight", facecolor="white")
        except ValueError:
            fig.savefig(out_path, dpi=145, facecolor="white")
    else:
        fig.savefig(out_path, dpi=145, facecolor="white")
    plt.close(fig)
    return out_path


def compile_encoding(enc: ChartEncoding, out_path: str, *, figsize=(11, 7.2)) -> str:
    """Render a ChartEncoding to `out_path` (PNG). Returns the path. Honours `encoding.facet`
    (small multiples: one panel per facet value)."""
    theme.use_theme()
    df = _df(enc)
    # NUMERIC SANITY: refuse an empty / all-NaN chart rather than ship a blank panel (the labour
    # Sahm-gap shipped with no data series). Raising here → the caller falls back to the deterministic
    # renderer, and if that also has no data the chart is dropped-and-logged, never shipped blank.
    yf = enc.encoding.y.field if enc.encoding.y else None
    n_valid = int(df[yf].notna().sum()) if (df is not None and yf and yf in df) else (0 if df is None else len(df))
    if n_valid < 2:
        raise ValueError(f"compile: empty/near-empty data for {enc.title[:40]!r} ({n_valid} valid points)")
    mark = enc.mark.value if hasattr(enc.mark, "value") else enc.mark
    if mark not in _DISPATCH:
        raise ValueError(f"compile: unsupported mark '{mark}'")

    fac = enc.encoding.facet
    facet_vals = list(dict.fromkeys(df[fac.field])) if (fac and fac.field in df) else None

    if facet_vals and len(facet_vals) > 1:
        # ── small multiples ──────────────────────────────────────────────────────────────────
        n = len(facet_vals)
        ncol = 2 if n <= 4 else 3
        nrow = (n + ncol - 1) // ncol
        fig, axes = plt.subplots(nrow, ncol, figsize=(6.4 * ncol, 4.2 * nrow),
                                 squeeze=False, sharex=True, sharey=True)
        flat = [a for row in axes for a in row]
        for a in flat:
            a.axis("off")
        for a, val in zip(flat, facet_vals):
            a.axis("on")
            sub = df[df[fac.field] == val]
            _draw_on_axes(a, enc, sub, fig, mark, panel=True)
            a.set_title(str(val), fontsize=11, fontweight="bold", color=theme.INK)
        ex, ey = enc.encoding.x, enc.encoding.y
        if ex:
            fig.supxlabel(ex.title or ex.field, fontsize=11)
        if ey and mark not in ("heatmap", "ridgeline"):
            fig.supylabel(ey.title or ey.field, fontsize=11)
        fig.suptitle(_cap(enc.title, 95), fontsize=15, fontweight="bold", x=0.01, ha="left", y=0.995)
        if enc.subtitle:
            fig.text(0.01, 0.945, _cap(enc.subtitle, 140), fontsize=10, color=theme.MUTED, ha="left")
        if enc.source_note:
            fig.text(0.99, 0.005, _cap(enc.source_note, 130), fontsize=7.8, color=theme.MUTED, ha="right")
        fig.tight_layout(rect=[0, 0.02, 1, 0.90])
        # clip in-panel marks so a connected-scatter's overflowing end labels can't distort the grid
        for a in flat:
            for art in a.get_children():
                try:
                    art.set_clip_on(True)
                except Exception:
                    pass
        return _savefig(fig, out_path, tight=False)

    # ── single panel ─────────────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize)
    _draw_on_axes(ax, enc, df, fig, mark, panel=False)
    ax.set_title(_cap(enc.title, 95), fontsize=15, fontweight="bold", loc="left",
                 pad=(20 if enc.subtitle else 8), wrap=True)
    if enc.subtitle:
        ax.text(0, 1.02, _cap(enc.subtitle, 150), transform=ax.transAxes, fontsize=10.5,
                color=theme.MUTED, va="bottom")
    if enc.source_note:
        ax.text(1.0, -0.13, _cap(enc.source_note, 130), transform=ax.transAxes, fontsize=7.8,
                color=theme.MUTED, va="top", ha="right")
    return _savefig(fig, out_path)
