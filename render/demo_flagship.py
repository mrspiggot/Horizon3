"""Demo: drive the reusable render layer on LIVE data to produce the flagship charts.

Proves the layer end-to-end (verified numbers -> render.charts -> polished figure) and shows the
prototype flaws fixed (the probability heatmap now auto-crops via prob_ylim; consistent theme).

Run with UMD's venv (has unified_market_data + matplotlib), Horizon3 on PYTHONPATH:
  PYTHONPATH=~/PycharmProjects/Horizon3 \
    ~/PycharmProjects/unified_market_data/.venv/bin/python -m render.demo_flagship EUR 1.90 out.png
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date

import asyncpg
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from render import charts  # noqa: E402
from unified_market_data.analysis.cb_meeting_calendars import meetings_for  # noqa: E402
from unified_market_data.analysis.curve_analytics import ois_forward_strip  # noqa: E402
from unified_market_data.analysis.curve_builder import build_ois_curve  # noqa: E402
from unified_market_data.analysis.rate_path_model import extract_meeting_forwards  # noqa: E402
from unified_market_data.services.nas_store import tsdb_dsn  # noqa: E402

CB_NAME = {"EUR": "ECB", "GBP": "Bank of England", "USD": "Federal Reserve",
           "JPY": "Bank of Japan", "CAD": "Bank of Canada"}


async def _pars(ccy: str) -> dict:
    conn = await asyncpg.connect(tsdb_dsn())
    r = await conn.fetchrow(
        "select tenors,rates from curve_snapshots where currency=$1 and curve_type='ois' "
        "order by timestamp desc limit 1", ccy)
    await conn.close()
    tn = r["tenors"] if isinstance(r["tenors"], list) else json.loads(r["tenors"])
    rt = r["rates"] if isinstance(r["rates"], list) else json.loads(r["rates"])
    return {t: v for t, v in zip(tn, rt) if v is not None}


def _distribution(meetings, spot):
    """Compound per-meeting steps into P(rate | after each meeting); return matrix + axes + paths."""
    states = {round(spot, 2): 1.0}
    snaps, fwd = [], []
    for m in meetings:
        ns: dict[float, float] = {}
        for rate, p in states.items():
            for dr, pp in [(-0.50, m.p_cut_50), (-0.25, m.p_cut_25), (0.0, m.p_hold), (0.25, m.p_hike_25)]:
                if pp <= 0:
                    continue
                k = round(rate + dr, 2)
                ns[k] = ns.get(k, 0) + p * pp
        tot = sum(ns.values())
        states = {k: v / tot for k, v in ns.items()}
        snaps.append(states.copy())
        fwd.append(m.forward_rate)
    grid = np.round(np.arange(min(min(s) for s in snaps), max(max(s) for s in snaps) + 0.25, 0.25), 2)
    M = np.zeros((len(grid), len(snaps)))
    for j, s in enumerate(snaps):
        for i, r in enumerate(grid):
            M[i, j] = s.get(round(r, 2), 0.0)
    modal = [grid[np.argmax(M[:, j])] for j in range(len(snaps))]
    mean = [sum(r * p for r, p in s.items()) for s in snaps]
    return M, grid, modal, mean, fwd


def _quantile(s, q):
    c = 0.0
    for k in sorted(s):
        c += s[k]
        if c >= q:
            return k
    return max(s)


def main(ccy: str, spot: float, out: str):
    pars = asyncio.run(_pars(ccy))
    curve = build_ois_curve(date(2026, 7, 10), pars.get("3M"), [], [], pars, currency=ccy)
    strip = ois_forward_strip(curve, date(2026, 7, 10), 40)
    meetings = extract_meeting_forwards(spot, strip, meeting_calendar=meetings_for(ccy))
    M, grid, modal, mean, fwd = _distribution(meetings, spot)
    labels = [m.meeting_date.strftime("%b-%y") for m in meetings]

    # per-meeting snapshots for the fan quantiles
    snaps = []
    states = {round(spot, 2): 1.0}
    for m in meetings:
        ns: dict[float, float] = {}
        for rate, p in states.items():
            for dr, pp in [(-0.50, m.p_cut_50), (-0.25, m.p_cut_25), (0.0, m.p_hold), (0.25, m.p_hike_25)]:
                if pp > 0:
                    k = round(rate + dr, 2)
                    ns[k] = ns.get(k, 0) + p * pp
        tot = sum(ns.values())
        states = {k: v / tot for k, v in ns.items()}
        snaps.append(states)
    x = list(range(len(snaps)))
    bands = [([_quantile(s, 0.10) for s in snaps], [_quantile(s, 0.90) for s in snaps], "10-90%"),
             ([_quantile(s, 0.25) for s in snaps], [_quantile(s, 0.75) for s in snaps], "25-75%")]

    fig = plt.figure(figsize=(15, 6.2))
    ax1 = fig.add_subplot(1, 2, 1)
    charts.probability_heatmap(
        ax1, M, labels, grid, modal=modal, mean=mean, forward=fwd, fig=fig,
        title=f"{ccy} — P(policy rate | meeting)", ylabel="policy rate (%)")
    ax2 = fig.add_subplot(1, 2, 2)
    charts.fan_chart(
        ax2, x, [_quantile(s, 0.50) for s in snaps], bands, mean=mean, forward=fwd, spot=spot,
        xticklabels=labels, title=f"{ccy} — implied policy-path fan", ylabel="policy rate (%)")
    fig.suptitle(
        f"{CB_NAME.get(ccy, ccy)} implied policy-rate distribution — live OIS + real meeting calendar "
        f"(rendered via render/, 2026-07-10)", fontsize=10.5, y=1.0)
    fig.savefig(out, dpi=140, bbox_inches="tight", facecolor="white")
    print("saved", out)


if __name__ == "__main__":
    a = sys.argv
    main(a[1] if len(a) > 1 else "EUR", float(a[2]) if len(a) > 2 else 1.90,
         a[3] if len(a) > 3 else "flagship.png")
