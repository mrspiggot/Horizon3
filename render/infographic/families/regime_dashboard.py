"""The `regime_dashboard` layout family — the §10 state principle as the page's spine.

Shape: headline + number-free thesis + the persona's KPI tiles + a row of §10 STATE BADGES (every key
input read as a state — where it sits vs its own history, and which way it is moving) + the macro
REGIME QUADRANT as the hero (level-extremity × momentum) + a "the read" note + provenance. Where
`decision_brief` shows levels, this family shows *states*: the badges and the quadrant both encode the
§10 tuple (level, direction, acceleration, context). Applies to the macro personas (central bank,
rates, forecaster, multi-asset) whose decision is a read of the whole regime.

The quadrant is a chart image; the badges are number-free directional labels — so no un-traced number
reaches the page. The KPI tiles carry the only figures, each a provenance-traced NumberObject.
"""
from __future__ import annotations

import base64
import os
import re
import sys
import tempfile
from pathlib import Path

from ..from_persona import (clean_meaning, first_sentence, humanise, persona_material,
                            reader_takeaway)
from ..gate import emit
from ..schema import Block, InfographicSpec, Layout

_PALETTE = ["#4C6EA8", "#D55E00", "#009E73", "#B8C4CE", "#D98A00"]
_TONES = ["mid", "up", "dn", "mid"]

# personas whose decision is fundamentally a read of the macro regime
_MACRO = {"central_bank_policymaker", "macro_rates_trader", "economist_forecaster",
          "equity_multiasset_pm"}

# the shared macro backdrop: eight variables read as §10 states (mirrors scripts/state_space_dashboard)
_VARS = [
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
    import pandas as pd
    cur = conn.cursor()
    cur.execute("SELECT timestamp, value FROM observations WHERE series_id=%s ORDER BY timestamp", (sid,))
    rows = cur.fetchall(); cur.close()
    if not rows:
        return None
    idx = pd.to_datetime([r[0] for r in rows]).tz_localize(None)
    s = pd.Series([float(r[1]) for r in rows], index=idx)
    s = s[~s.index.duplicated(keep="last")]
    return s.resample("MS").last()


def macro_regime_png(conn) -> str | None:
    """Render the §10 macro-regime quadrant (8 macro variables as states) → base64 PNG, or None."""
    sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
    import numpy as np
    from unified_market_data.analysis.state import state_tuple
    from ...studio.families.state_space import StatePoint, StateSpaceSpec, render_state_space

    dgs10, dgs2 = _series(conn, "DGS10"), _series(conn, "DGS2")
    points = []
    for label, sid, unit, kind in _VARS:
        s = (dgs10 - dgs2).dropna() if sid == "__SLOPE__" else _series(conn, sid)
        if s is None or len(s.dropna()) < 40:
            continue
        v = (100.0 * (s / s.shift(12) - 1.0)) if kind == "yoy" else s
        v = v.dropna()
        st = state_tuple(list(v.values), step=3, context_window=120)
        std = float(np.std(v.values[-120:], ddof=1)) or 1.0
        momz = (st.direction / std) if st.direction == st.direction else float("nan")
        reading = f"{st.level:.1f}{unit} · {st.zscore:+.1f}σ · mom {momz:+.1f}σ/3m"
        points.append(StatePoint(label=label, x=st.zscore, y=momz,
                                 accel=(st.acceleration or 0.0), reading=reading))
    if len(points) < 3:
        return None
    spec = StateSpaceSpec(
        title="Where every macro input sits in its own cycle",
        subtitle=("Eight variables read as §10 STATES, not levels: each plotted by how extreme it is "
                  "versus its own 10-year history (x) against its 3-month momentum (y)."),
        xlabel="level vs own 10-year history  (z-score, σ)",
        ylabel="momentum: 3-month change  (σ)",
        source="Source: FRED, NY Fed ACM.  State via §10 state_tuple (step=3m, 10-year window).",
        footer="Every value is executed on data — nothing on this chart is authored.")
    out = os.path.join(tempfile.gettempdir(), "ais_regime.png")
    try:
        render_state_space(points, spec, out)
        return base64.b64encode(Path(out).read_bytes()).decode()
    except Exception:
        return None
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


# reader-facing names for the terse macro input ids (their authored `meaning` is empty). Scoped to the
# badges so it can't mis-expand a field elsewhere; `tpN` handled by rule.
_BADGE_LABEL = {
    "g": "GDP growth", "du": "Unemployment (Δ)", "dur": "Unemployment (Δ)", "v": "Vacancy rate",
    "u": "Unemployment", "pi": "Inflation", "sahm": "Sahm gauge", "spread": "Yield-curve spread",
    "cpi": "CPI", "policy": "Policy rate", "gap": "Output gap", "rstar": "r*",
    "breakeven": "Breakeven inflation", "real_gdp": "Real GDP", "potential_gdp": "Potential GDP",
    "nfci": "Financial conditions (NFCI)", "risk": "Risk subindex", "credit": "Credit subindex",
    "leverage": "Leverage subindex",
}


def _badge_label(iid: str) -> str:
    if iid in _BADGE_LABEL:
        return _BADGE_LABEL[iid]
    m = re.match(r"tp(\d+)$", iid)
    if m:
        return f"{m.group(1)}y term premium"
    return humanise(iid)


def _state_words(st) -> tuple[str, str]:
    """(level word, momentum word) from a §10 State — number-free, so the badge cites no figure."""
    z, d = getattr(st, "zscore", None), getattr(st, "direction", None)
    lvl = ("elevated" if z > 0.75 else "depressed" if z < -0.75 else "middling") if z is not None else ""
    mom = ("rising" if d > 1e-4 else "falling" if d < -1e-4 else "flat") if d is not None else ""
    return lvl, mom


def _badges(mat: dict, limit: int = 5) -> list[Block]:
    """One §10 state badge per key input, deduped across the persona's models."""
    out, seen = [], set()
    for mid in mat["p"].get("models", []):
        latest = mat["runs"].get(mid, {}).get("latest")
        if latest is None:
            continue
        for iid, st in latest.inputs.items():
            if iid in seen or isinstance(st, (int, float)):
                continue
            lvl, mom = _state_words(st)
            if not lvl and not mom:
                continue
            seen.add(iid)
            words = ", ".join(w for w in (lvl, mom) if w)
            out.append(Block(id=f"badge_{iid}", type="state_badge",
                             title=f"{_badge_label(iid)}: {words}",
                             tone=("dn" if mom == "rising" else "up" if mom == "falling" else "")))
            if len(out) >= limit:
                return out
    return out


def spec_from_persona(persona_id: str, conn) -> tuple[InfographicSpec, set[str]]:
    if persona_id not in _MACRO:
        raise ValueError(f"{persona_id}: not a macro/regime persona — no regime_dashboard")
    mat = persona_material(persona_id, conn)
    p, numbers, salient, meanings = mat["p"], mat["numbers"], mat["salient"], mat["meanings"]

    dimensioned = [k for k in salient
                   if any(c in "%$×σ°" or c.isalpha() for c in numbers[k].rendered())]
    tiles = [Block(id=f"kpi{i}", type="kpi_tile",
                   title=clean_meaning(meanings.get(k, ""), humanise(k.split(".", 1)[1])),
                   numbers=[numbers[k]], tone=_TONES[i % len(_TONES)])
             for i, k in enumerate(dimensioned[:4])]
    if len(tiles) < 3:
        raise ValueError(f"{persona_id}: <3 dimensioned salient numbers for the KPI row")

    badges = _badges(mat)
    if len(badges) < 3:
        raise ValueError(f"{persona_id}: <3 state badges — inputs carry no readable §10 state")

    png = macro_regime_png(conn)
    if not png:
        raise ValueError(f"{persona_id}: macro regime quadrant did not render")
    hero = Block(id="regime", type="chart_embed",
                 title="Every macro input as a §10 state — extremity (x) against momentum (y).",
                 chart_png=png)

    thesis = Block(id="thesis", type="thesis_callout",
                   text=first_sentence(p.get("summary_template", "")))
    blocks = [thesis, *tiles, *badges, hero]
    take = reader_takeaway(p.get("summary_template", ""))
    if take:
        blocks.append(Block(id="note", type="note", title="The read", text=take))
    src_line = f"Source: {', '.join(mat['source_labels']) or 'UMD'}."
    if mat["as_of"]:
        src_line += f"  Data as of {mat['as_of']}."
    blocks.append(Block(id="src", type="source", text=src_line))

    spec = InfographicSpec(
        persona=p["name"], title=p["title"], deck=p.get("decision", ""),
        as_of=mat["as_of"], family="regime_dashboard",
        layout=Layout(accent=_PALETTE[0], palette=_PALETTE),
        blocks=blocks)
    return spec, set(numbers.keys())


def render_persona(persona_id: str, conn, out_png: str) -> str:
    spec, valid = spec_from_persona(persona_id, conn)
    return emit(spec, out_png, valid_sources=valid)
