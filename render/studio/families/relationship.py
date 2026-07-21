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
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch
from matplotlib import patheffects as pe

from ... import theme
from ..from_model import _label, _parse_ref, _value

INK, GRID = "#16161d", "#d7d7de"
_HALO = [pe.Stroke(linewidth=3.2, foreground="white"), pe.Normal()]
_TXT_HALO = [pe.Stroke(linewidth=2.2, foreground="white"), pe.Normal()]
_UNIT_HINTS = ("%", "pp", "bp", "index", "$", "ratio", "σ", "z-", "prob")
_CMAP = "cividis"   # perceptually uniform + colourblind-safe time ramp
_HOT = "#e0a63a"    # hot-corner accent (low unemployment × high inflation)


@dataclass
class RelationshipSpec:
    title: str
    subtitle: str
    xlabel: str
    ylabel: str
    x_key: str
    y_key: str
    mode: str                      # "fit" | "path" | "regime"
    cbar_label: str
    source: str
    footer: str
    annotations: list[dict] = field(default_factory=list)
    # regime (inflation-anchoring) rendering — jurisdiction calibration from the graph, threaded in
    regimes: str = ""              # "inflation_anchoring" enables the regime-separated Phillips render
    infl_axis: str = "y"           # which axis carries inflation (for the anchoring split + hot corner)
    target: float | None = None    # this jurisdiction's inflation target
    u_star: float | None = None    # this jurisdiction's Phillips hot-corner unemployment threshold
    hot_infl: float | None = None  # this jurisdiction's hot-corner inflation threshold


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
    if spec.mode not in ("fit", "path", "regime"):
        p.append("mode must be 'fit', 'path' or 'regime' — bare dots (neither) are forbidden")
    if spec.x_key not in df.columns or spec.y_key not in df.columns:
        p.append("x/y column missing from data")
    elif len(df.dropna(subset=[spec.x_key, spec.y_key])) < 10:
        p.append("fewer than 10 valid (x, y) points — not a relationship")
    if not spec.cbar_label.strip():
        p.append("time ramp has no label")
    return p


def _anchoring_regimes(infl: np.ndarray, target: float, *, band: float = 1.5,
                       win: int = 36, min_len: int = 48) -> list[list]:
    """Contiguous inflation-anchoring eras: anchored where the trailing `win`-point mean inflation sits
    within `band` of the jurisdiction's target. Short runs (< min_len points, ~4yr monthly) are absorbed
    into a neighbour so an era is a coherent PERIOD, not a flicker — a few meaningful regimes (like the
    primer's ~3), not a dozen slivers. Returns [[i0, i1_exclusive, anchored_bool], …]."""
    s = pd.Series(infl, dtype=float)
    win = min(win, max(6, len(s) // 4))                        # short series get a shorter smoother
    min_len = 30                                               # ~2.5yr: merges noise slivers but KEEPS the
    #                                                            dramatic 2022 de-anchoring (~4yr) everywhere
    roll = s.rolling(win, min_periods=max(6, win // 3)).mean().bfill().ffill().to_numpy()
    anchored = np.abs(roll - target) <= band
    n = len(anchored)
    runs, i = [], 0
    while i < n:
        j = i
        while j < n and anchored[j] == anchored[i]:
            j += 1
        runs.append([i, j, bool(anchored[i])])
        i = j
    def _coalesce(rs):
        out = []
        for r in rs:
            if out and out[-1][2] == r[2]:
                out[-1][1] = r[1]                  # same state as previous → one era
            else:
                out.append([r[0], r[1], r[2]])
        return out

    changed = True
    while changed and len(runs) > 1:
        changed = False
        for k, r in enumerate(runs):
            if r[1] - r[0] < min_len:
                if k + 1 < len(runs):
                    runs[k + 1][0] = r[0]          # absorb forward
                else:
                    runs[k - 1][1] = r[1]          # last run → absorb backward
                runs.pop(k)
                runs = _coalesce(runs)             # a removed sliver can leave two same-state neighbours
                changed = True
                break
    return _coalesce(runs)


def _render_regime_phillips(fig, ax, d: pd.DataFrame, spec: RelationshipSpec) -> None:
    """The regime-separated Phillips trajectory: inflation-anchoring eras each in their own colour with
    their own short-run fit (the curve HOLDS within a regime and SHIFTS between them — Friedman-Phelps),
    a faint chronological path, 5-year year-markers, direction arrows, and this jurisdiction's own
    hot-corner shaded at its u*. Colour encodes REGIME, not a continuous ramp — maximally discriminating."""
    x = d[spec.x_key].to_numpy(float)          # unemployment
    y = d[spec.y_key].to_numpy(float)          # inflation
    dts = pd.to_datetime(d["date"]); years = dts.dt.year.to_numpy()
    infl = y if spec.infl_axis == "y" else x
    target = spec.target if spec.target is not None else 2.0

    # zoom to the data (so JP's narrow range isn't a dot in the corner), then shade the hot corner
    xpad = max(0.3, float(np.ptp(x)) * 0.08); ypad = max(0.4, float(np.ptp(y)) * 0.08)
    x0, x1 = x.min() - xpad, x.max() + xpad
    y0, y1 = min(y.min(), target) - ypad, y.max() + ypad
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.axhline(target, color="#8f8f98", lw=1.0, ls=(0, (4, 3)), zorder=1)
    ax.annotate(f"target {target:.0f}%", xy=(x1, target), xytext=(-4, 3), textcoords="offset points",
                fontsize=8.5, color="#6a6a72", ha="right", va="bottom")
    if spec.u_star is not None and spec.hot_infl is not None:
        ax.fill_between([x0, spec.u_star], spec.hot_infl, y1, color=_HOT, alpha=0.12, zorder=0)
        ax.annotate("hot corner\n(tight labour, high inflation)", xy=((x0 + spec.u_star) / 2, y1),
                    xytext=(0, -6), textcoords="offset points", fontsize=8.0, color="#9a7a25",
                    ha="center", va="top")

    # faint full chronological path (the loops read as time) + direction arrows
    ax.plot(x, y, color="#c6c6ce", lw=1.0, alpha=0.75, zorder=1, solid_capstyle="round")
    for frac in (0.30, 0.60, 0.86):
        k = int(frac * (len(x) - 1))
        if k + 1 < len(x):
            ax.add_patch(FancyArrowPatch((x[k], y[k]), (x[k + 1], y[k + 1]), arrowstyle="-|>",
                         mutation_scale=13, lw=0, color="#8a8a93", alpha=0.9, zorder=6))

    # per-era points + short-run fits; colour = regime
    handles, anchored_k = [], 0
    for i0, i1, anch in _anchoring_regimes(infl, target):
        xs_, ys_ = x[i0:i1], y[i0:i1]
        yr0, yr1 = int(years[i0]), int(years[i1 - 1])
        if anch:
            col = theme.cat(anchored_k); anchored_k += 1
            ax.scatter(xs_, ys_, s=27, color=col, edgecolor="white", lw=0.35, zorder=4, alpha=0.92)
            lbl = f"anchored {yr0}–{yr1}"
            if len(xs_) >= 12 and float(np.ptp(xs_)) > 0.2:
                b1, b0 = np.polyfit(xs_, ys_, 1)
                gx = np.linspace(xs_.min(), xs_.max(), 50)
                ax.plot(gx, b0 + b1 * gx, color=col, lw=2.6, zorder=5, path_effects=_HALO)
                lbl += f"   slope {b1:+.2f}"
            handles.append(Line2D([0], [0], marker="o", color=col, lw=2.4, markersize=7,
                                  markeredgecolor="white", label=lbl))
        else:
            ax.scatter(xs_, ys_, s=20, color="#b7b7c0", edgecolor="white", lw=0.3, zorder=3, alpha=0.75)
            handles.append(Patch(facecolor="#b7b7c0", edgecolor="none", label=f"de-anchored {yr0}–{yr1}"))

    # year-markers along the path — every 10y for a long history (US 1948→) so labels don't collide,
    # every 5y for the shorter post-2000 series.
    step = 10 if (int(years.max()) - int(years.min())) > 34 else 5
    lo = (int(years.min()) // step) * step
    for tick in range(lo, int(years.max()) + 1, step):
        cand = np.where(years == tick)[0]
        if len(cand):
            k = cand[0]
            ax.scatter([x[k]], [y[k]], s=14, color=INK, zorder=8)
            ax.annotate(str(tick), (x[k], y[k]), xytext=(4, 3), textcoords="offset points",
                        fontsize=7.6, color=INK, zorder=9, path_effects=_TXT_HALO)

    # start (open ring) + latest (filled), each labelled with its year
    ax.scatter([x[0]], [y[0]], s=64, facecolor="white", edgecolor=INK, lw=1.7, zorder=8)
    ax.annotate(f"start {int(years[0])}", (x[0], y[0]), xytext=(7, -11), textcoords="offset points",
                fontsize=8.2, color=INK, zorder=9, path_effects=_TXT_HALO)
    ax.scatter([x[-1]], [y[-1]], s=150, color="#c0392b", edgecolor="white", lw=1.6, zorder=10)
    ax.annotate(f"latest {int(years[-1])}", (x[-1], y[-1]), xytext=(9, 4), textcoords="offset points",
                fontsize=9.0, color="#c0392b", fontweight="bold", zorder=11, path_effects=_TXT_HALO)

    # pooled fit as the CONTRAST (the misleading flat line the eras explain away)
    pb1, pb0 = np.polyfit(x, y, 1)
    pr = np.corrcoef(x, y)[0, 1]
    gx = np.linspace(x.min(), x.max(), 50)
    ax.plot(gx, pb0 + pb1 * gx, color="#9a9aa2", lw=1.6, ls=(0, (6, 4)), zorder=2)
    handles.append(Line2D([0], [0], color="#9a9aa2", lw=1.6, ls="--",
                          label=f"pooled fit — flat (R²={pr**2:.2f})"))

    leg = ax.legend(handles=handles, loc="upper right", fontsize=8.4, frameon=True, framealpha=0.95,
                    edgecolor="#c8c8d0", title="regime (each its own short-run curve)", title_fontsize=8.6)
    leg.get_frame().set_linewidth(0.8)


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

    sc = None
    if spec.mode == "regime":
        _render_regime_phillips(fig, ax, d, spec)
    elif spec.mode == "path":
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

    # emphasise + label the latest observation (offset clear of the fit line). The regime render draws
    # its own start/latest markers, so skip this generic one there.
    if spec.mode != "regime":
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
    if spec.mode != "regime":
        ax.margins(0.06)

    # colour→date colourbar for the continuous ramps; regime mode encodes time as discrete eras + a
    # legend + year-markers instead, so it takes no colourbar.
    if sc is not None:
        cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.045)
        if "date" in d and len(order) > 1:
            dts = pd.to_datetime(d["date"]).reset_index(drop=True)
            n = len(order)
            pos = sorted({int(round(t * (n - 1))) for t in (0.0, 0.25, 0.5, 0.75, 1.0)})
            cbar.set_ticks([order[i] for i in pos])
            cbar.set_ticklabels([dts.iloc[i].strftime("%b %Y") for i in pos])   # month+year, never bare/duplicate years
        cbar.set_label(spec.cbar_label, fontsize=10)
        cbar.ax.tick_params(labelsize=8.5)

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
    dts = pd.to_datetime(df["date"]).sort_values()
    gap = dts.diff().dt.days.median() if len(dts) > 1 else None
    cadence = ("daily" if gap and gap <= 3 else "weekly" if gap and gap <= 10
               else "monthly" if gap and gap <= 45 else "quarterly" if gap and gap <= 110
               else "annual" if gap else "")
    span = f"{dts.iloc[0]:%b %Y}–{dts.iloc[-1]:%b %Y}"
    cbar_label = f"observation date ({cadence + ', ' if cadence else ''}{span})"
    insight = " ".join((chart.get("insight") or "").split())
    subtitle = insight if len(insight) <= 200 else insight[:197] + "…"

    # Regime-separated Phillips (inflation-anchoring): pull THIS jurisdiction's calibration from the graph
    # (soft-coded, per-jurisdiction) and fill the {price_index} label token so the axis reads HICP for EU,
    # CPI for the US/GB/JP — never a hardcoded gauge.
    instance = run.get("instance") or "US"
    regimes = dc.get("regimes", "")
    mode = "regime" if regimes else ("path" if dc.get("path") else "fit")
    target = u_star = hot_infl = None
    xlabel, ylabel = dc.get("xlabel", xcol), dc.get("ylabel", ycol)
    if regimes:
        try:
            from ...jurisdiction import fill_frame_tokens
            from ...jurisdiction_facts import facts
            calib = facts(instance).get("calibration", {})
            target = calib.get("inflation_target_pct")
            u_star = calib.get("phillips_u_star_pct")
            hot_infl = calib.get("phillips_hot_infl_pct")
            xlabel, ylabel = fill_frame_tokens(xlabel, instance), fill_frame_tokens(ylabel, instance)
        except Exception as exc:   # never fail the chart on a lookup — fall back to the fit render
            print(f"REGIME PHILLIPS — {instance}: calibration lookup failed ({exc}); plain fit",
                  file=__import__("sys").stderr)
            mode = "fit"
    spec = RelationshipSpec(
        title=dc.get("title") or chart_id,
        subtitle=dc.get("subtitle") or subtitle,
        xlabel=xlabel, ylabel=ylabel,
        x_key=xcol, y_key=ycol, mode=mode,
        cbar_label=cbar_label,
        source=dc.get("source", f"Model: {model.get('name', model.get('model_id', ''))}. "
                                f"Source: {', '.join(sorted({i.get('db_source','') for i in model.get('inputs', []) if i.get('db_source')}))}."),
        footer="Every value is executed on data — nothing on this chart is authored by the model.",
        regimes=regimes, infl_axis=dc.get("inflation_axis", "y"),
        target=target, u_star=u_star, hot_infl=hot_infl,
    )
    return df, spec
