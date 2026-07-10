"""Proof of the catalog->render wiring: render a MODEL'S charts straight from its declared
`visualizations` block, with no per-model chart code.

The bridge reads ois_implied_path.yaml's visualizations (policy_path_fan, policy_path_heatmap),
maps each to a render primitive, and composes the figure from the supplied verified numbers.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

import numpy as np

from render import from_catalog
from render.demo_flagship import _distribution, _pars, _quantile
from unified_market_data.analysis.cb_meeting_calendars import meetings_for
from unified_market_data.analysis.curve_analytics import ois_forward_strip
from unified_market_data.analysis.curve_builder import build_ois_curve
from unified_market_data.analysis.rate_path_model import extract_meeting_forwards


def main(ccy: str, spot: float, out: str):
    pars = asyncio.run(_pars(ccy))
    curve = build_ois_curve(date(2026, 7, 10), pars.get("3M"), [], [], pars, currency=ccy)
    strip = ois_forward_strip(curve, date(2026, 7, 10), 40)
    meetings = extract_meeting_forwards(spot, strip, meeting_calendar=meetings_for(ccy))
    M, grid, modal, mean, fwd = _distribution(meetings, spot)
    labels = [m.meeting_date.strftime("%b-%y") for m in meetings]

    # rebuild per-meeting snapshots for the fan quantiles
    snaps, states = [], {round(spot, 2): 1.0}
    for m in meetings:
        ns: dict[float, float] = {}
        for r, p in states.items():
            for dr, pp in [(-0.50, m.p_cut_50), (-0.25, m.p_cut_25), (0.0, m.p_hold), (0.25, m.p_hike_25)]:
                if pp > 0:
                    k = round(r + dr, 2)
                    ns[k] = ns.get(k, 0) + p * pp
        tot = sum(ns.values())
        states = {k: v / tot for k, v in ns.items()}
        snaps.append(states)
    x = list(range(len(snaps)))

    # data shaped to each chart_type's data contract, keyed by the viz `id` in the catalog
    data_by_viz_id = {
        "policy_path_fan": {
            "x": x, "median": [_quantile(s, 0.50) for s in snaps],
            "bands": [([_quantile(s, 0.10) for s in snaps], [_quantile(s, 0.90) for s in snaps], "10-90%"),
                      ([_quantile(s, 0.25) for s in snaps], [_quantile(s, 0.75) for s in snaps], "25-75%")],
            "mean": mean, "forward": fwd, "spot": spot, "xticklabels": labels,
        },
        "policy_path_heatmap": {
            "matrix": M, "xticklabels": labels, "y_levels": np.asarray(grid),
            "modal": modal, "mean": mean, "forward": fwd,
        },
    }
    from_catalog.render_model(
        "ois_implied_path", data_by_viz_id, out,
        suptitle=f"{ccy} implied policy path — charts generated FROM the catalog visualizations spec "
                 f"(ois_implied_path.yaml) via render/from_catalog")
    print("saved", out)


if __name__ == "__main__":
    a = sys.argv
    main(a[1] if len(a) > 1 else "EUR", float(a[2]) if len(a) > 2 else 1.90,
         a[3] if len(a) > 3 else "catalog_render.png")
