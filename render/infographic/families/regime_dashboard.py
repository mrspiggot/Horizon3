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

from ..from_persona import (clean_meaning, dashboard_read, dashboard_thesis, dashboard_tile_keys,
                            humanise, persona_material)
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


def _macro_backdrop_points(conn) -> list:
    """The shared 8-variable macro backdrop as §10 states — the fallback when a persona's own inputs
    can't fill the quadrant."""
    import numpy as np
    from unified_market_data.analysis.state import state_tuple
    from ...studio.families.state_space import StatePoint

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
    return points


def _persona_state_points(mat: dict) -> list:
    """The persona's OWN model inputs as §10 states — reconstruct each input's level series from the
    run history and read it with the same `state_tuple` math the macro backdrop uses. So the quadrant
    shows the variables the body narrates, not a recycled macro panel, and cannot contradict it."""
    import numpy as np
    from unified_market_data.analysis.state import state_tuple
    from ...studio.families.state_space import StatePoint

    points, seen = [], set()
    for mid in mat["p"].get("models", []):
        run = mat["runs"].get(mid, {})
        hist, latest = run.get("history") or [], run.get("latest")
        if latest is None or len(hist) < 40:
            continue
        for iid in getattr(latest, "inputs", {}) or {}:
            if iid in seen:
                continue
            series = []
            for rec in hist:
                obj = (getattr(rec, "inputs", {}) or {}).get(iid)
                lvl = getattr(obj, "level", obj)
                if isinstance(lvl, (int, float)):
                    series.append(float(lvl))
            if len(series) < 40:
                continue
            try:
                st = state_tuple(series, step=3, context_window=120)
                std = float(np.std(series[-120:], ddof=1)) or 1.0
                momz = st.direction / std
            except Exception:
                continue
            seen.add(iid)
            reading = f"{st.level:.2f} · {st.zscore:+.1f}σ · mom {momz:+.1f}σ/3m"
            points.append(StatePoint(label=_badge_label(iid), x=st.zscore, y=momz,
                                     accel=(st.acceleration or 0.0), reading=reading))
    return points


def macro_regime_png(conn, mat: dict | None = None) -> str | None:
    """Render the §10 regime quadrant → base64 PNG. Plots the PERSONA's own model inputs when they
    fill the quadrant (≥3 readable states); otherwise the shared 8-variable macro backdrop."""
    sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
    from ...studio.families.state_space import StateSpaceSpec, render_state_space

    points, own = [], False
    if mat is not None:
        points = _persona_state_points(mat)
        own = len(points) >= 3
    if not own:
        points = _macro_backdrop_points(conn)
    if len(points) < 3:
        return None
    subtitle = ("Each of this decision's own model inputs read as a §10 STATE, not a level: how "
                "extreme it is versus its own history (x) against its 3-month momentum (y).") if own else \
               ("Eight variables read as §10 STATES, not levels: each plotted by how extreme it is "
                "versus its own 10-year history (x) against its 3-month momentum (y).")
    spec = StateSpaceSpec(
        title=("Where this decision's inputs sit in their own cycle" if own else
               "Where every macro input sits in its own cycle"),
        subtitle=subtitle,
        xlabel="level vs own history  (z-score, σ)",
        ylabel="momentum: 3-month change  (σ)",
        source="Source: FRED, NY Fed ACM.  State via §10 state_tuple (step=3m).",
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


# A badge reads the raw input STATE (z-score over the model's window); the body reads the model's
# INTERPRETATION, often against a recent range. They can clash — "CPI: elevated, rising" beside a body
# that says inflation is low and its momentum has bled out. We suppress a badge ONLY when the body
# clearly says the opposite for the same concept (the opposite cue present, the confirming cue absent),
# never on ambiguity: a factual badge is not convicted on a fuzzy read, and the floor still holds.
_FALLING = re.compile(r"\b(fall\w*|fell|declin\w*|deceler\w*|eas(?:e|ed|ing)|cool\w*|bled out|"
                      r"drop\w*|lower|receded|soften\w*|softer|slow\w*|subsid\w*)\b", re.I)
_RISING = re.compile(r"\b(ris\w*|rose|acceler\w*|climb\w*|higher|hotter|surg\w*|jump\w*|firm\w*)\b", re.I)
_LOWWORD = re.compile(r"\b(low|lowest|bottom|subdued|depressed|below|weak\w*|muted)\b", re.I)
_HIGHWORD = re.compile(r"\b(high|highest|elevated|above|strong\w*|hot)\b", re.I)

# the body and the badge often use different words for one concept (a "CPI" badge vs an "inflation"
# body). Expand a label to its synonym group so the concept's sentences are actually found.
_SYN = [
    {"cpi", "inflation", "pce", "price", "prices", "disinflation", "inflationary"},
    {"unemployment", "jobless", "payroll", "payrolls", "labour", "labor", "employment"},
    {"vacancy", "vacancies", "openings", "tightness"},
    {"growth", "gdp", "output", "activity"},
    {"policy", "funds", "rate", "rates"},
    {"spread", "slope", "curve", "premium"},
    {"vol", "volatility", "vix"},
    {"gap", "slack"},
]


def _concept_words(label: str) -> set[str]:
    ws = set(re.findall(r"[a-z]{3,}", label.lower())) - {"rate", "index", "gauge", "the"}
    for grp in _SYN:
        if ws & grp:
            ws = ws | grp
    return ws


def _badge_contradicts_body(label: str, lvl: str, mom: str, body: str) -> bool:
    concept = _concept_words(label)
    if not concept or not body:
        return False
    sents = [s for s in re.split(r"(?<=[.!?])\s+", body) if any(w in s.lower() for w in concept)]
    if not sents:
        return False
    t = " ".join(sents)
    if mom == "rising" and _FALLING.search(t) and not _RISING.search(t):
        return True
    if mom == "falling" and _RISING.search(t) and not _FALLING.search(t):
        return True
    if lvl == "elevated" and _LOWWORD.search(t) and not _HIGHWORD.search(t):
        return True
    if lvl == "depressed" and _HIGHWORD.search(t) and not _LOWWORD.search(t):
        return True
    return False


def _badges(mat: dict, limit: int = 5, *, article: dict | None = None, floor: int = 3) -> list[Block]:
    """One §10 state badge per key input, deduped across the persona's models. A badge that clearly
    contradicts the finished body is suppressed (down to the floor), so the dashboard cannot say the
    opposite of the article beside it."""
    body = (article or {}).get("full_text") or ""
    cands, seen = [], set()
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
            label = _badge_label(iid)
            cands.append({"iid": iid, "label": label, "lvl": lvl, "mom": mom,
                          "contra": _badge_contradicts_body(label, lvl, mom, body)})
    clean = [c for c in cands if not c["contra"]]
    kept = clean + [c for c in cands if c["contra"]][: max(0, floor - len(clean))]
    for c in cands:
        if c["contra"] and c not in kept:
            print(f"BADGE suppressed (contradicts body) — {c['label']}: "
                  f"{', '.join(w for w in (c['lvl'], c['mom']) if w)}", file=sys.stderr)
    out = []
    for c in kept[:limit]:
        words = ", ".join(w for w in (c["lvl"], c["mom"]) if w)
        out.append(Block(id=f"badge_{c['iid']}", type="state_badge", title=f"{c['label']}: {words}",
                         tone=("dn" if c["mom"] == "rising" else "up" if c["mom"] == "falling" else "")))
    return out


def spec_from_persona(persona_id: str, conn, *, article: dict | None = None) -> tuple[InfographicSpec, set[str]]:
    if persona_id not in _MACRO:
        raise ValueError(f"{persona_id}: not a macro/regime persona — no regime_dashboard")
    mat = persona_material(persona_id, conn)
    p, numbers, meanings = mat["p"], mat["numbers"], mat["meanings"]

    tile_keys = dashboard_tile_keys(mat, article, n=4)
    tiles = [Block(id=f"kpi{i}", type="kpi_tile",
                   title=clean_meaning(meanings.get(k, ""), humanise(k.split(".", 1)[1])),
                   numbers=[numbers[k]], tone=_TONES[i % len(_TONES)])
             for i, k in enumerate(tile_keys)]
    if len(tiles) < 3:
        raise ValueError(f"{persona_id}: <3 dimensioned salient numbers for the KPI row")

    badges = _badges(mat, article=article)
    if len(badges) < 3:
        raise ValueError(f"{persona_id}: <3 state badges — inputs carry no readable §10 state")

    png = macro_regime_png(conn, mat)
    if not png:
        raise ValueError(f"{persona_id}: macro regime quadrant did not render")
    hero = Block(id="regime", type="chart_embed",
                 title="Every input as a §10 state — extremity (x) against momentum (y).",
                 chart_png=png)

    thesis = Block(id="thesis", type="thesis_callout", text=dashboard_thesis(mat, article))
    blocks = [thesis, *tiles, *badges, hero]
    take = dashboard_read(mat, article)
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


def render_persona(persona_id: str, conn, out_png: str, **kw) -> str:
    spec, valid = spec_from_persona(persona_id, conn, **kw)
    return emit(spec, out_png, valid_sources=valid)
