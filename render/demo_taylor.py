"""Capstone: the reaction-function insight rendered via render/ — the Taylor-rule prescription vs the
actual policy rate over time, the policy-stance gap shaded. Live FRED inputs, date-aligned."""
from __future__ import annotations

import asyncio
import sys

import asyncpg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from render import charts  # noqa: E402
from unified_market_data.analysis.reaction_function import output_gap_pct, taylor_prescription  # noqa: E402
from unified_market_data.services.nas_store import tsdb_dsn  # noqa: E402


async def _series(conn, sid):
    rows = await conn.fetch(
        "select timestamp, value from observations where series_id=$1 order by timestamp", sid)
    return [(r["timestamp"].date(), float(r["value"])) for r in rows]


def _at(ts_list, d):
    """Value at-or-before date d (the date-alignment discipline)."""
    v = None
    for dd, vv in ts_list:
        if dd <= d:
            v = vv
        else:
            break
    return v


async def main(out: str):
    conn = await asyncpg.connect(tsdb_dsn())
    gdp = await _series(conn, "GDPC1")
    pot = await _series(conn, "GDPPOT")
    pce = await _series(conn, "PCEPILFE")
    dff = await _series(conn, "FEDFUNDS")        # monthly fed funds — decades of history
    await conn.close()

    labels, presc, actual = [], [], []
    for d, g in gdp[-48:]:                       # last 48 actual GDP quarters (~12 yrs)
        p = _at(pot, d)
        pce_now = _at(pce, d)
        pce_yr = _at(pce, d.replace(year=d.year - 1))
        a = _at(dff, d)
        if None in (p, pce_now, pce_yr, a):
            continue
        infl = 100.0 * (pce_now / pce_yr - 1.0)
        presc.append(taylor_prescription(infl, output_gap_pct(g, p), r_star_pct=0.7))
        actual.append(a)
        labels.append(f"{d.year}Q{(d.month - 1) // 3 + 1}")

    x = list(range(len(labels)))
    lo = [min(a, pp) for a, pp in zip(actual, presc)]
    hi = [max(a, pp) for a, pp in zip(actual, presc)]
    fig, ax = plt.subplots(figsize=(12, 6))
    charts.overlay_lines(
        ax, x,
        [("Taylor-1993 prescription", presc, "solid"),
         ("Actual fed funds (FEDFUNDS)", actual, "dashed")],
        band=(lo, hi, "policy-stance gap"), xticklabels=labels,
        title="US — Taylor-rule prescription vs actual policy rate  (live FRED, rendered via render/)",
        ylabel="rate (%)")
    ax.text(0.01, 0.02, "rule above actual = policy easier than the rule prescribes",
            transform=ax.transAxes, fontsize=8, color="#555")
    fig.savefig(out, dpi=140, bbox_inches="tight", facecolor="white")
    print("saved", out, "| quarters:", len(labels))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "taylor.png"))
