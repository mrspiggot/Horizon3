"""The cross-country scorecard render — the flagship exhibit of the steering rebuild.

Runs a jurisdiction-generic indicator model across its instances (run_model_instances) and lays the
economies side by side as an indicators × countries heatmap: each cell shows the LEVEL, coloured by that
indicator's §10 state — the z-score of the latest value against the country's OWN history, so "hot/cold
vs its own norm" is comparable across economies. A growth×inflation regime label sits under each column.
This is the "state of the major economies" article's hero, grounded entirely in real UMD data.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .. import graph_corpus, theme  # noqa: E402

_CB_SHORT = {"US": "Fed", "EU": "ECB", "GB": "BoE", "JP": "BoJ", "CH": "SNB", "CA": "BoC", "AU": "RBA"}

# (output field, row label, unit) — the indicators to show, in reading order
_ROWS = [
    ("inflation_pct", "Inflation (YoY)", "%"),
    ("unemployment_pct", "Unemployment", "%"),
    ("policy_rate_pct", "Policy rate", "%"),
    ("real_policy_rate_pct", "Real policy rate", "%"),
    ("long_yield_pct", "10y yield", "%"),
    ("leading_indicator", "Leading indicator", ""),
]


def _zscore(hist, field) -> tuple[float | None, float | None]:
    """(latest level, z-score of latest vs the series' own history)."""
    vals = [r.outputs.get(field) for r in hist if r.outputs.get(field) is not None]
    if len(vals) < 8:
        return (vals[-1] if vals else None, None)
    a = np.asarray(vals, float)
    sd = float(a.std()) or 1.0
    return (float(a[-1]), float((a[-1] - a.mean()) / sd))


def _regime(latest) -> str:
    o = latest.outputs
    cli, infl = o.get("leading_indicator", 100.0), o.get("inflation_pct", 0.0)
    growing, hot = cli >= 100.0, infl >= 2.5
    return ("reflation" if growing and hot else "goldilocks" if growing else
            "stagflation" if hot else "slowdown")


def scorecard_png(conn, out_path: str, model_id: str = "economies_scorecard") -> str | None:
    runs = graph_corpus.run_model_instances(model_id, conn)
    inst = runs.get("instances") or {}
    if len(inst) < 2:
        return None
    order = [j for j in ("US", "EU", "GB", "JP", "CH", "CA", "AU") if j in inst]
    cbs = [inst[j].get("cb", j) for j in order]
    levels = np.full((len(_ROWS), len(order)), np.nan)
    zs = np.full((len(_ROWS), len(order)), np.nan)
    for cj, j in enumerate(order):
        hist = inst[j].get("history") or []
        for ri, (field, _lbl, _u) in enumerate(_ROWS):
            lv, z = _zscore(hist, field)
            if lv is not None:
                levels[ri, cj] = lv
            if z is not None:
                zs[ri, cj] = z

    theme.use_theme()
    nrow, ncol = len(_ROWS), len(order)
    fig, ax = plt.subplots(figsize=(2.6 + 1.9 * ncol, 2.6 + 0.72 * nrow))
    m = float(np.nanpercentile(np.abs(zs), 95)) or 2.0
    ax.imshow(zs, cmap="RdBu_r", vmin=-m, vmax=m, aspect="auto")
    ax.set_aspect("auto")                                  # fill the width — never square cells
    for ri, (_field, _lbl, u) in enumerate(_ROWS):
        for cj in range(ncol):
            lv = levels[ri, cj]
            if not np.isnan(lv):
                txt = f"{lv:.2f}{u}" if u else f"{lv:.1f}"
                ax.text(cj, ri, txt, ha="center", va="center", fontsize=13, fontweight="bold",
                        color=theme.INK)
    ax.set_xticks(range(ncol))
    ax.set_xticklabels([f"{_CB_SHORT.get(j, j)}\n{j}" for j in order], fontsize=11, fontweight="bold")
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks(range(nrow))
    ax.set_yticklabels([lbl for _f, lbl, _u in _ROWS], fontsize=11.5)
    ax.set_xticks(np.arange(-.5, ncol, 1), minor=True)
    ax.set_yticks(np.arange(-.5, nrow, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2.5)
    ax.tick_params(which="both", length=0)
    ax.set_ylim(nrow - 0.5, -0.5)
    # regime label under each column
    for cj, j in enumerate(order):
        reg = _regime(inst[j]["latest"]) if inst[j].get("latest") else ""
        ax.text(cj, nrow - 0.5 + 0.14 * nrow, reg, ha="center", va="top", fontsize=10.5,
                style="italic", fontweight="bold", color=theme.MUTED, clip_on=False)
    ax.text(-0.5, nrow - 0.5 + 0.14 * nrow, "regime:", ha="right", va="top", fontsize=10,
            color=theme.MUTED, clip_on=False)
    fig.text(0.16, 0.955, "The major economies, side by side", fontsize=18, fontweight="bold",
             ha="left", va="top", color=theme.INK)
    fig.text(0.16, 0.905, "Each cell is the latest reading; colour = distance from that economy's own "
                          "history (red high, blue low).", fontsize=10.5, ha="left", va="top",
             color=theme.MUTED)
    fig.text(0.5, 0.015, "Source: FRED, ECB, ONS, IMF, OECD via UMD — one model, run across four central banks.",
             ha="center", fontsize=8, color=theme.MUTED)
    fig.subplots_adjust(left=0.16, right=0.98, top=0.80, bottom=0.14)
    fig.savefig(out_path, dpi=145, facecolor="white")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    import psycopg2
    c = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                         user="postgres", password="devpassword")
    print(scorecard_png(c, "/tmp/scorecard.png"))
    c.close()
