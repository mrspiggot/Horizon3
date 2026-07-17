"""The Fact Sheet — §10 applied to the EVIDENCE, so the Narrator reads the model instead of guessing.

§10's principle is that no professional reads a variable as a bare number: they read its level, its
direction and speed, its acceleration, and its context. The Executor already does this for every model
INPUT. Nobody ever did it for the model's OUTPUT — the thing the article is actually about.

So the Narrator (§06 role 5) was handed, per chart, exactly two strings: the chart's title and a
hand-authored `insight` from the catalog. That is all it has ever known about a series it is asked to
describe. It is not careless when it writes "r* drifted down through the 2010s, and more recently up";
it is doing the only thing possible — reciting the canonical literature story, because it has never
seen the series HLW actually produced in this run (r* is +1.06, essentially its 2010 level, and has
fallen for three years).

This reads the executed output series out of the Output table and returns the same §10 state the model
itself consumes, plus the three facts a claim is actually made of:

    superlative -> min/max WITH THEIR DATES        ("the most restrictive since the GFC")
    regime      -> current sign, and when it last flipped   ("the slope below zero")
    direction   -> the signed change over 12m and 36m       ("more recently up")

Those are the three the Judge adjudicates. Handing the Narrator the same facts the Judge will check it
against is the point: prevention, not detection. The Judge stays as the backstop, but a Narrator that
can see `max +2.27pp (2024-08)` cannot write "the most restrictive since the GFC" about +0.18pp.

Every value here is computed from executed output. This module authors nothing.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path.home() / "PycharmProjects/unified_market_data/src"))
from unified_market_data.analysis.state import state_tuple  # noqa: E402

from .model_store import output_series  # noqa: E402


def _delta(pts: list[tuple[date, float]], months: int) -> float | None:
    """Signed change over the trailing `months`, or None when the series is too short to say."""
    if not pts:
        return None
    last_d, last_v = pts[-1]
    cutoff = date(last_d.year - months // 12, last_d.month, 1)
    prior = [(d, v) for d, v in pts if d <= cutoff]
    return (last_v - prior[-1][1]) if prior else None


def _last_flip(pts: list[tuple[date, float]]) -> tuple[date | None, int]:
    """When the series last crossed zero, and how many observations it has held its sign.
    A regime claim ("the slope below zero") is about a SPAN, not a point."""
    if not pts:
        return None, 0
    sign = pts[-1][1] >= 0
    for i in range(len(pts) - 1, 0, -1):
        if (pts[i - 1][1] >= 0) != sign:
            return pts[i][0], len(pts) - i
    return None, len(pts)


def fact_sheet(conn, run_id: str, name: str, *, unit: str = "") -> dict | None:
    """The §10 state of one executed output series. None if it has no points."""
    pts = [(d, v) for d, v in output_series(conn, run_id, name) if v is not None]
    if not pts:
        return None
    st = state_tuple([{"timestamp": d.isoformat(), "value": v} for d, v in pts], step=1,
                     context_window=min(60, len(pts)))
    lo_d, lo_v = min(pts, key=lambda x: x[1])
    hi_d, hi_v = max(pts, key=lambda x: x[1])
    flip_d, held = _last_flip(pts)
    return {
        "output": name, "unit": unit,
        "first": pts[0][0], "last": pts[-1][0], "n": len(pts),
        "level": st.level,
        "d12": _delta(pts, 12), "d36": _delta(pts, 36),
        "min": lo_v, "min_at": lo_d, "max": hi_v, "max_at": hi_d,
        "percentile": st.percentile, "zscore": st.zscore,
        "sign": "positive" if pts[-1][1] >= 0 else "negative",
        "flipped_at": flip_d, "held_n": held,
    }


def _fmt(v, spec="+.2f"):
    return "n/a" if v is None or v != v else format(v, spec)


def render_sheet(fs: dict) -> str:
    """One compact block per output — the Narrator's evidence, in the model's own units."""
    u = fs["unit"] or ""
    lines = [f"  {fs['output']} ({u or '-'}) — executed {fs['first']} → {fs['last']}, {fs['n']} points",
             f"      level      {_fmt(fs['level'])}{u} as of {fs['last']}",
             f"      direction  {_fmt(fs['d12'])}{u} over 12m · {_fmt(fs['d36'])}{u} over 36m",
             f"      range      min {_fmt(fs['min'])}{u} ({fs['min_at']}) · "
             f"max {_fmt(fs['max'])}{u} ({fs['max_at']})",
             f"      context    {fs['percentile']:.0%} percentile of its own history"
             if fs["percentile"] == fs["percentile"] else "      context    n/a"]
    if fs["flipped_at"]:
        lines.append(f"      regime     {fs['sign']} since {fs['flipped_at']} ({fs['held_n']} points)")
    else:
        lines.append(f"      regime     {fs['sign']} throughout its history")
    return "\n".join(lines)


def sheets_for_run(conn, run_id: str, outputs: list[dict]) -> str:
    """Every output of one run, as evidence the Narrator may cite about SHAPE."""
    out = []
    for o in outputs or []:
        fs = fact_sheet(conn, run_id, o.get("name"), unit=o.get("unit", ""))
        if fs:
            out.append(render_sheet(fs))
    return "\n".join(out)
