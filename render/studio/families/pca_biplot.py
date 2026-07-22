"""PCA biplot — a graph-driven ML view for a model that carries SEVERAL quantitative outputs over time.

The Phillips regime chart proved the pattern: run an ML transform on the executed data, DRAW the
structure, and RETURN it as a ChartInsight so the prose is driven by what the picture shows. This does
the same for dimensionality: it standardises a model's multi-output state, runs PCA to two components,
and draws a BIPLOT — each period a point (coloured by time), each output a loading vector, the latest
period a diamond. The reader sees which outputs co-move (one story or several), how much of the variation
two axes capture, and where 'now' sits in that reduced space.

Selection is DATA-SHAPE / graph driven (`transform: pca` on a chart whose model has ≥4 quantitative
outputs) — never persona- or jurisdiction-specific. A model with deeper coverage earns the richer view
by its declared shape, not because of which economy it is. Deterministic (random_state where it matters,
sign-fixed axes) so the same run always yields the same picture and words.
"""
from __future__ import annotations

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects as pe

from ..from_model import _value

INK = "#1a1a1a"
MUTED = "#8a8a8a"
MIN_FEATURES = 4
MIN_ROWS = 40


@dataclass
class PcaBiplotSpec:
    title: str
    features: list           # display labels, in column order of the matrix
    subtitle: str = ""
    source: str = ""
    footer: str = ""


def _matrix(model: dict, run: dict) -> tuple[list[str], list[str], np.ndarray, np.ndarray] | None:
    """(field_names, labels, dates, X) — the model's quantitative outputs over history. None if the
    shape does not support PCA (too few numeric outputs or rows)."""
    from ...infographic.from_persona import humanise
    hist = run.get("history") or []
    outs = [o for o in (model.get("outputs") or [])
            if str(o.get("unit", "")).strip() not in ("0/1", "0..1", "prob", "share")]
    names = [o["name"] for o in outs]
    if not names and hist:
        # Declared outputs unavailable on this run object — derive the feature names from the executed
        # records themselves (the keys present on every point). Keeps the transform self-sufficient.
        common = None
        for r in hist:
            keys = set(getattr(r, "outputs", {}) or {})
            common = keys if common is None else (common & keys)
        names = sorted(common or [])
    if len(names) < MIN_FEATURES:
        return None
    labels = [humanise(n) for n in names]
    rows, dates = [], []
    for r in hist:
        vals = [_value(r, "output", n, "level") for n in names]
        if all(v is not None for v in vals):
            rows.append([float(v) for v in vals])
            dates.append(str(r.as_of)[:10])
    if len(rows) < MIN_ROWS:
        return None
    return names, labels, np.array(dates), np.asarray(rows, dtype=float)


def _pca(X: np.ndarray):
    """Standardise, PCA→2. Sign-fix each component so its largest-magnitude loading is positive (a
    deterministic, reader-stable orientation). Returns (scores, loadings, explained_variance_ratio)."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    Xs = StandardScaler().fit_transform(X)
    p = PCA(n_components=2, random_state=0).fit(Xs)
    comps = p.components_.copy()
    scores = p.transform(Xs)
    for k in range(2):
        j = int(np.argmax(np.abs(comps[k])))
        if comps[k, j] < 0:
            comps[k] *= -1.0
            scores[:, k] *= -1.0
    return scores, comps, p.explained_variance_ratio_


def pca_insight(model: dict, run: dict, chart_id: str):
    """Compute the biplot's structure as a ChartInsight the prose can narrate (variance captured, which
    outputs define each axis, where 'now' sits). Pure + deterministic. None on any failure."""
    from ..insight import ChartInsight, CitableFact
    try:
        built = _matrix(model, run)
        if not built:
            return None
        names, labels, dates, X = built
        scores, comps, evr = _pca(X)
        pc1, pc2 = float(evr[0] * 100), float(evr[1] * 100)
        # which outputs define each axis (largest |loading|)
        def _top(k):
            order = np.argsort(-np.abs(comps[k]))
            return [(labels[j], float(comps[k][j])) for j in order[:3]]
        t1, t2 = _top(0), _top(1)
        s1 = scores[:, 0]
        latest_pct = float((s1 < s1[-1]).mean() * 100)
        lead = ", ".join(f"{l} ({v:+.2f})" for l, v in t1)
        contrast = ", ".join(f"{l} ({v:+.2f})" for l, v in t2)
        findings = [
            f"The {len(names)} outputs are NOT {len(names)} independent stories: the first two principal "
            f"components capture {pc1 + pc2:.0f}% of all variation ({pc1:.0f}% + {pc2:.0f}%), so the state "
            f"is really two-dimensional.",
            f"Axis 1 ({pc1:.0f}% of variance) is the COMMON factor — it loads together on {lead}; these "
            f"outputs co-move, and one number tracks most of the picture.",
            f"Axis 2 ({pc2:.0f}%) is the residual contrast — {contrast} — what moves when the common "
            f"factor does not.",
            f"The latest reading sits at the {latest_pct:.0f}th percentile of the common factor over "
            f"{dates[0][:4]}–{dates[-1][:4]} — {'stretched high' if latest_pct >= 80 else 'stretched low' if latest_pct <= 20 else 'mid-range'}.",
        ]
        head = (f"{len(names)} outputs collapse onto 2 axes explaining {pc1 + pc2:.0f}% of the variation — "
                f"a dominant common factor plus one contrast, not {len(names)} separate signals.")
        citable = [CitableFact(label="PCA axis-1 variance explained", value=pc1,
                               source=f"{model.get('model_id','')}.pca_pc1", unit="%", fmt="{:.0f}"),
                   CitableFact(label="PCA axis-2 variance explained", value=pc2,
                               source=f"{model.get('model_id','')}.pca_pc2", unit="%", fmt="{:.0f}")]
        return ChartInsight(kind="pca", headline=head, findings=findings, citable=citable,
                            facts={"pc1": pc1, "pc2": pc2, "features": labels,
                                   "loadings_pc1": t1, "loadings_pc2": t2, "latest_pct": latest_pct})
    except Exception as exc:
        print(f"PCA INSIGHT failed: {type(exc).__name__}: {exc}", file=__import__("sys").stderr)
        return None


def spec_from_run(model: dict, run: dict, chart_id: str, persona_name: str = "") \
        -> tuple[pd.DataFrame, PcaBiplotSpec] | None:
    """Build (df, PcaBiplotSpec) from a `transform: pca` chart + executed run. The df carries the raw
    output matrix (date + one column per output); render_pca_biplot computes the PCA from it."""
    chart = next((c for c in run.get("charts", []) if c.get("id") == chart_id), None)
    history = run.get("history") or []
    if chart is None or not history:
        return None
    dc = chart.get("data_contract", {}) or {}
    if dc.get("transform") != "pca":
        return None
    built = _matrix(model, run)
    if not built:
        return None
    names, labels, dates, X = built
    df = pd.DataFrame(X, columns=labels)
    df.insert(0, "date", pd.to_datetime(dates))
    insight = " ".join((chart.get("insight") or "").split())
    src = dc.get("source") or (f"Model: {model.get('name', model.get('model_id',''))}. "
                               f"PCA of {len(labels)} standardised outputs, {dates[0]}–{dates[-1]}.")
    spec = PcaBiplotSpec(
        title=dc.get("title") or chart_id, features=labels,
        subtitle=dc.get("subtitle") or insight, source=src,
        footer="PCA is executed on the data — the axes, loadings and position are computed, not authored.")
    return df, spec


def render_pca_biplot(df: pd.DataFrame, spec: PcaBiplotSpec, out: str) -> str:
    """Draw the biplot: period scores (coloured by time) + output loading vectors + the latest period."""
    from ... import theme
    theme.use_theme()
    labels = spec.features
    X = df[labels].to_numpy(float)
    dates = pd.to_datetime(df["date"])
    scores, comps, evr = _pca(X)
    pc1, pc2 = evr[0] * 100, evr[1] * 100

    fig, ax = plt.subplots(figsize=(11, 7.6))
    order = np.arange(len(scores))
    sc = ax.scatter(scores[:, 0], scores[:, 1], c=order, cmap="viridis", s=16,
                    alpha=0.72, edgecolor="white", linewidth=0.2, zorder=3)
    cbar = fig.colorbar(sc, ax=ax, pad=0.015, fraction=0.045)
    pos = sorted({int(round(t * (len(dates) - 1))) for t in (0.0, 0.5, 1.0)})
    cbar.set_ticks([order[i] for i in pos])
    cbar.set_ticklabels([dates.iloc[i].strftime("%Y") for i in pos])
    cbar.set_label("observation date", fontsize=9.5)
    cbar.ax.tick_params(labelsize=8.5)

    # loading vectors — scaled per-axis to each score range so arrows read against the cloud even when
    # axis-1 variance dwarfs axis-2 (they would otherwise pile onto the x-axis).
    sx = (float(np.abs(scores[:, 0]).max()) or 1.0) * 0.9
    sy = (float(np.abs(scores[:, 1]).max()) or 1.0) * 0.9
    tips = [(comps[0, j] * sx, comps[1, j] * sy) for j in range(len(labels))]
    # stagger labels of near-parallel loadings (the common-factor arrows overlap) by pushing each label
    # out to a distinct radius along its own direction — so NFCI / Risk / Leverage don't collide.
    for j, lab in enumerate(labels):
        vx, vy = tips[j]
        ax.annotate("", xy=(vx, vy), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color="#b3341f", lw=2.0, mutation_scale=15), zorder=6)
        r = 1.10 + 0.11 * j                      # each successive label sits a little further out
        ax.text(vx * r, vy * r, lab, color="#b3341f", fontsize=10.5, fontweight="bold",
                ha="center", va="center", zorder=7,
                path_effects=[pe.withStroke(linewidth=2.8, foreground="white")])

    # the latest period — the diamond the reader looks for
    ax.scatter([scores[-1, 0]], [scores[-1, 1]], s=170, marker="D", color=INK,
               edgecolor="white", linewidth=1.8, zorder=8)
    ax.annotate(f"latest {dates.iloc[-1].strftime('%b %Y')}", (scores[-1, 0], scores[-1, 1]),
                xytext=(9, 5), textcoords="offset points", fontsize=9.5, fontweight="bold", color=INK,
                zorder=9, path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
    ax.axhline(0, color="#c8c8d0", lw=0.9, zorder=1)
    ax.axvline(0, color="#c8c8d0", lw=0.9, zorder=1)

    # a little vertical breathing room so the cloud isn't jammed against the axis-1 line
    ylo, yhi = float(scores[:, 1].min()), float(scores[:, 1].max())
    ax.set_ylim(ylo - 0.5, yhi + 0.9)
    ax.set_xlabel(f"principal axis 1 — {pc1:.0f}% of variance (the common factor)", fontsize=11)
    ax.set_ylabel(f"principal axis 2 — {pc2:.0f}% (the contrast)", fontsize=11)
    fig.text(0.075, 0.955, spec.title, fontsize=18, fontweight="bold", color=INK)
    if spec.subtitle:
        import textwrap
        sub = "\n".join(textwrap.wrap(spec.subtitle, width=112))
        fig.text(0.075, 0.905, sub, fontsize=10.6, color="#4a4a52", va="top", linespacing=1.3)
    if spec.source:
        fig.text(0.075, 0.028, spec.source, fontsize=8.2, color=MUTED)
    if spec.footer:
        fig.text(0.075, 0.010, spec.footer, fontsize=8.2, color=MUTED, style="italic")
    theme.style_axes(ax, grid_axis="both")
    fig.subplots_adjust(left=0.075, right=0.90, top=0.83, bottom=0.11)
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    return out
