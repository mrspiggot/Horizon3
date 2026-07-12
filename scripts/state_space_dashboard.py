"""State-space family: the §10 macro-regime quadrant.

Reads ~8 macro variables as §10 STATES (state_tuple) and plots them at once in
level-extremity (z-score) × momentum (standardised 3m change) space — the regime map a
macro strategist reads. One render_state_space() code path.

    ~/venv/bin/python scripts/state_space_dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np      # noqa: E402
import pandas as pd     # noqa: E402
import psycopg2         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
from unified_market_data.analysis.state import state_tuple             # noqa: E402
from render.studio.families.state_space import (                       # noqa: E402
    StatePoint, StateSpaceSpec, render_state_space)

OUT = Path("/private/tmp/claude-501/-Users-richardwalker-PycharmProjects-Horizon3/"
           "228d447a-ca1c-45a3-8270-88c34b5c527a/scratchpad/state_space")

# (label, series_id, unit, kind)  kind: 'level' | 'yoy' | special handled below
VARS = [
    ("Core PCE inflation", "PCEPILFE", "%", "yoy"),
    ("CPI inflation", "CPIAUCSL", "%", "yoy"),
    ("Unemployment", "UNRATE", "%", "level"),
    ("Fed funds", "FEDFUNDS", "%", "level"),
    ("10y Treasury yield", "DGS10", "%", "level"),
    ("2s10s slope", "__SLOPE__", "pp", "level"),
    ("10y term premium", "ACMTP10", "pp", "level"),
    ("Equity vol (VIX)", "VIXCLS", "pt", "level"),
]


def _series(conn, sid):
    cur = conn.cursor()
    cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s ORDER BY timestamp", (sid,))
    rows = cur.fetchall(); cur.close()
    if not rows:
        return None
    idx = pd.to_datetime([r[0] for r in rows]).tz_localize(None)
    s = pd.Series([float(r[1]) for r in rows], index=idx)
    s = s[~s.index.duplicated(keep="last")]
    return s.resample("MS").last()   # month-start last observation


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    dgs10, dgs2 = _series(conn, "DGS10"), _series(conn, "DGS2")
    points = []
    for label, sid, unit, kind in VARS:
        if sid == "__SLOPE__":
            s = (dgs10 - dgs2).dropna()
        else:
            s = _series(conn, sid)
        if s is None or len(s.dropna()) < 40:
            print(f"skip {label}: insufficient data"); continue
        v = (100.0 * (s / s.shift(12) - 1.0)) if kind == "yoy" else s
        v = v.dropna()
        st = state_tuple(list(v.values), step=3, context_window=120)
        ctx = v.values[-120:]
        std = float(np.std(ctx, ddof=1)) or 1.0
        momz = (st.direction / std) if st.direction == st.direction else float("nan")
        disp = st.level / 100.0 if unit == "bp" else st.level      # show OAS in %
        u = "%" if unit == "bp" else unit
        reading = f"{disp:.1f}{u} · {st.zscore:+.1f}σ · mom {momz:+.1f}σ/3m"
        points.append(StatePoint(label=label, x=st.zscore, y=momz, accel=(st.acceleration or 0.0),
                                 reading=reading))
        print(f"OK  {label:22} z={st.zscore:+.2f}  mom={momz:+.2f}σ  accel={st.acceleration:+.2f}")

    spec = StateSpaceSpec(
        title="Where every macro input sits in its own cycle",
        subtitle=("Eight variables read as §10 STATES, not levels: each plotted by how extreme it is versus its own 10-year "
                  "history (x) against its 3-month momentum (y). Colour = accelerating or decelerating."),
        xlabel="level vs own 10-year history  (z-score, σ)",
        ylabel="momentum: 3-month change  (σ)",
        source="Variables: core PCE & CPI (YoY), unemployment, fed funds, 10y yield, 2s10s slope, 10y term premium, equity vol (VIX).  "
               "Source: FRED, NY Fed ACM.  State via §10 state_tuple (step=3m, 10-year window).",
        footer="Every value is executed on data — nothing on this chart is authored by the model.")
    out = OUT / "macro_regime.png"
    render_state_space(points, spec, str(out))
    print(f"\nstate-space -> {out}  ({len(points)} variables)")


if __name__ == "__main__":
    main()
