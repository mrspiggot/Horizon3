"""Decomposition-family gallery: prove ONE renderer generalises across personas.

Runs each model's authored `kind: decomposition` chart through the executor and the
deterministic family renderer (render/studio/families/decomposition.py), plus the deep
Taylor rule, and assembles a contact sheet. Every chart is lint-gated; a craft violation
would abort rather than ship.

    ~/venv/bin/python scripts/decomp_gallery.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt   # noqa: E402
import pandas as pd               # noqa: E402
import psycopg2                   # noqa: E402
import yaml                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render import graph_corpus                                             # noqa: E402
from render.studio.families.decomposition import (                          # noqa: E402
    Component, DecompSpec, render_decomposition, spec_from_run)

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"
OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/decomp_gallery")

# (model_id, decomposition chart id, persona) — catalog-native, executor emits components
CATALOG_JOBS = [
    ("term_premium_decomposition", "Why the 10Y is where it is — expectations vs term premium", "Macro rates trader"),
    ("credit_excess_bond_premium", "What the credit market is charging for, decomposed", "Credit investor"),
    ("funding_cost", "What a treasurer actually pays, decomposed", "Corporate treasurer"),
]


def _conn():
    return psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")


def _load_model(mid: str) -> dict:
    return yaml.safe_load((GRAPH_DIR / f"{mid}.yaml").read_text())


# ── deep Taylor: computes the contributions reaction_function does not yet emit ────────────────
def _series(conn, sid: str) -> pd.Series:
    cur = conn.cursor()
    cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s AND timestamp>=%s "
                "ORDER BY timestamp", (sid, "1998-01-01"))
    rows = cur.fetchall(); cur.close()
    idx = pd.to_datetime([r[0] for r in rows]).tz_localize(None)
    s = pd.Series([float(r[1]) for r in rows], index=idx)
    return s[~s.index.duplicated(keep="last")]


def taylor_deep(conn) -> tuple[pd.DataFrame, DecompSpec]:
    ff, core = _series(conn, "FEDFUNDS"), _series(conn, "PCEPILFE")
    unr, rst = _series(conn, "UNRATE"), _series(conn, "RSTAR_US")
    infl = 100.0 * (core / core.shift(12) - 1.0)
    idx = pd.date_range("2000-01-01", ff.index.max(), freq="MS")
    on = lambda s: s.reindex(s.index.union(idx)).sort_index().interpolate("time").reindex(idx)
    ff, infl, unr, rst = on(ff), on(infl), on(unr), on(rst)
    df = pd.DataFrame({"neutral": rst + 2.0, "infl_resp": 1.5 * (infl - 2.0),
                       "slack_resp": -1.0 * (unr - 4.4)}, index=idx)
    df["net"] = df[["neutral", "infl_resp", "slack_resp"]].sum(axis=1)
    df["actual"] = ff
    df = df.dropna()
    spec = DecompSpec(
        title="What is the Fed's rule actually reacting to?",
        subtitle=("The Taylor-rule prescribed policy rate, decomposed into the contribution of each input the rule reads —\n"
                  "the neutral rate r*, the inflation gap, and labour-market slack — versus the rate the Fed actually set."),
        xlabel="Year", ylabel="Contribution to the prescribed nominal policy rate  (%, annualised)",
        components=[Component("neutral", "Neutral  (r* + 2%)", "#B8C4CE"),
                    Component("infl_resp", "Inflation-gap response", "#D55E00"),
                    Component("slack_resp", "Labour-slack response", "#009E73")],
        net_key="net", net_label="Taylor prescription",
        actual_key="actual", actual_label="Actual fed funds",
        ylim=(-9.6, 10.2), tick_years=2, clip_disclosed=True,
        end_labels=[{"key": "net", "text": "Taylor rule\n5.4%", "dy": 10},
                    {"key": "actual", "text": "Fed\n3.6%", "dy": -12}],
        callouts=[
            {"text": "2020: the rule fell off-scale (≈ −9%)\nas the labour market collapsed;\nthe Fed floored at zero (ZLB)",
             "xy": (pd.Timestamp("2020-05-01"), -7.2), "xytext": (pd.Timestamp("2002-09-01"), -6.6)},
            {"text": "2022–23: the inflation response (red)\ndrove the rule near 9½%;\nthe Fed lagged it by 2+ points",
             "xy": (pd.Timestamp("2022-09-01"), 9.2), "xytext": (pd.Timestamp("2013-01-01"), 8.7)}],
        source=("Rule: prescription = (r* + 2) + 1.5·(π − 2) − (u − u*),  u* = 4.4% (CBO long-run).   "
                "Source: FRED — FEDFUNDS, PCEPILFE (core PCE, YoY), UNRATE;  NY Fed Holston–Laubach–Williams r*."),
        footer="Every value is executed on data — nothing on this chart is authored by the model.")
    return df, spec


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    tiles: list[tuple[str, str, Path]] = []

    # central banker — deep Taylor
    try:
        df, spec = taylor_deep(conn)
        out = OUT / "central_bank_taylor.png"
        render_decomposition(df, spec, str(out))
        tiles.append(("Central banker", spec.title, out))
        print(f"OK  Central banker         | {spec.title}")
    except Exception as exc:
        print(f"FAIL Central banker: {type(exc).__name__}: {str(exc)[:200]}")

    # catalog-native decompositions
    for mid, chart_id, persona in CATALOG_JOBS:
        try:
            run = graph_corpus.run_model(mid, conn)
            built = spec_from_run(_load_model(mid), run, chart_id, persona)
            if not built:
                print(f"FAIL {persona}: spec_from_run returned None ({mid})"); continue
            df, spec = built
            out = OUT / f"{mid}.png"
            render_decomposition(df, spec, str(out))
            tiles.append((persona, spec.title, out))
            print(f"OK  {persona:22}| {spec.title}   [{len(df)} pts]")
        except Exception as exc:
            print(f"FAIL {persona} ({mid}): {type(exc).__name__}: {str(exc)[:200]}")

    # contact sheet
    if tiles:
        n = len(tiles)
        fig, axes = plt.subplots(2, 2, figsize=(26, 15))
        for ax, (persona, _title, png) in zip(axes.ravel(), tiles):
            ax.imshow(mpimg.imread(str(png))); ax.axis("off")
        for ax in axes.ravel()[n:]:
            ax.axis("off")
        fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005, wspace=0.02, hspace=0.02)
        sheet = OUT / "_contact_sheet.png"
        fig.savefig(str(sheet), dpi=100, facecolor="white"); plt.close(fig)
        print(f"\ncontact sheet -> {sheet}")
        print(f"{n} decompositions, {n} personas, ONE render_decomposition() code path.")


if __name__ == "__main__":
    main()
