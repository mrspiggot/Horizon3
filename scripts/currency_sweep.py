"""Currency sweep: the decomposition family across Fed / ECB / BoE / BoJ.

The SAME inflation-Taylor decomposition — prescribed nominal rate = neutral (r*+2%) +
1.5·(π−2) — run across four central banks from each one's bound policy-rate + CPI series,
faceted as small multiples. The divergence between them is the insight: who fought the
2022 inflation, who did not, and Japan's deflationary regime apart from the rest.

    ~/venv/bin/python scripts/currency_sweep.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import pandas as pd     # noqa: E402
import psycopg2         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.studio.families.decomposition import (   # noqa: E402
    Component, render_decomposition_faceted)

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/currency_sweep")

R_STAR, TARGET = 0.5, 2.0   # common neutral real rate + 2% target (stated simplification)

# (central bank, ccy, policy-rate series, source, CPI series, source)
CBS = [
    ("Federal Reserve  (USD)", "DFF", "fred", "CPIAUCSL", "fred"),
    ("European Central Bank  (EUR)", "ECBDFR", "fred", "CP0000EZ19M086NEST", "fred"),
    ("Bank of England  (GBP)", "BOE_IUDBEDR", "boe", "GBRCPIALLMINMEI", "fred"),
    ("Bank of Japan  (JPY)", "IRSTCI01JPM156N", "fred", "JPNCPIALLMINMEI", "fred"),
]


def _series(conn, sid: str, src: str) -> pd.Series:
    cur = conn.cursor()
    cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s AND source=%s "
                "ORDER BY timestamp", (sid, src))
    rows = cur.fetchall(); cur.close()
    idx = pd.to_datetime([r[0] for r in rows]).tz_localize(None)
    s = pd.Series([float(r[1]) for r in rows], index=idx)
    return s[~s.index.duplicated(keep="last")]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    idx = pd.date_range("2000-01-01", "2026-06-01", freq="MS")
    panels = []
    for cb, prate, psrc, cpi, csrc in CBS:
        pol = _series(conn, prate, psrc)
        px = _series(conn, cpi, csrc)
        infl = 100.0 * (px / px.shift(12) - 1.0)
        # interpolate INTERIOR gaps only — never extrapolate past a series' last real observation
        # (else a stale CPI would fabricate a flat inflation tail — the masking we refuse to do).
        on = lambda s: (s.reindex(s.index.union(idx)).sort_index()
                        .interpolate("time", limit_area="inside").reindex(idx))
        pol_m, infl_m = on(pol), on(infl)
        df = pd.DataFrame({
            "neutral": R_STAR + TARGET,
            "infl_resp": 1.5 * (infl_m - TARGET),
        }, index=idx)
        df["net"] = df["neutral"] + df["infl_resp"]   # NaN where inflation data has run out
        df["actual"] = pol_m
        df = df.dropna(subset=["actual"])              # keep the (real) policy tail; rule stops where CPI does
        panels.append((cb, df))
        print(f"OK  {cb:32}| {len(df)} pts | latest rule {df['net'].iloc[-1]:.1f}% vs actual {df['actual'].iloc[-1]:.1f}%")

    components = [Component("neutral", "Neutral  (r* + 2% target)", "#B8C4CE"),
                 Component("infl_resp", "Inflation-gap response  1.5·(π − 2)", "#D55E00")]
    out = OUT / "currency_sweep.png"
    render_decomposition_faceted(
        panels, components, "net", "Rule-prescribed rate", "actual", "Actual policy rate",
        title="One rule, four central banks: who fought the inflation?",
        subtitle=("The same inflation-Taylor rule — prescribed rate = (r* + 2%) + 1.5·(π − 2) —\n"
                  "run across four central banks, each from its own policy rate and CPI."),
        ylabel="Contribution to the prescribed rate  (%)",
        source=("Rule assumes a common neutral r* + target = 2.5% for comparability.  Policy: DFF, ECBDFR, BOE Bank Rate, BoJ call rate.  "
                "CPI (YoY): US CPI-U, euro-area HICP, UK CPI, Japan CPI.  Sources: FRED, Bank of England."),
        footer="Every value is executed on data — nothing on this chart is authored by the model.  (Each rule stops where its CPI does: UK 2025-03, Japan 2021-06.)",
        out=str(out), ncols=2, tick_years=6)
    print(f"\nfaceted sweep -> {out}")


if __name__ == "__main__":
    main()
