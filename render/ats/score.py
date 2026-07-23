"""Scoring — auditable, deterministic-dominant, one LLM call.

Most dimensions are computed from data (imminence, data-readiness, novelty, persona balance, user intent,
evergreen fit); three that need judgement (market impact, angle novelty, zeitgeist salience) come from a
SINGLE structured-output call over the compact candidate index (so it can judge them relatively). They
combine as a weighted sum + a "hits multiple dimensions" bonus; data-readiness==0 excludes a candidate
outright. The top-3 is then chosen greedily with a same-persona diversity penalty. Every candidate keeps
its full breakdown so the briefing can show WHY each card surfaced.
"""
from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, Field

from . import coverage
from .schema import CandidateTrigger, ScoreBreakdown

# audited weights (one place to tune). deterministic dims dominate; user-intent is a strong prior.
WEIGHTS = {
    "imminence": 0.20, "data_readiness": 0.16, "market_impact": 0.16, "novelty": 0.12,
    "persona_coverage": 0.08, "user_intent": 0.14, "evergreen_fit": 0.06,
    "angle_novelty": 0.04, "zeitgeist_salience": 0.04,
}
_JUDGED = ("market_impact", "angle_novelty", "zeitgeist_salience")
_LOOKAHEAD = 14.0
_BONUS_DIMS, _BONUS_AT, _BONUS = ("imminence", "data_readiness", "market_impact"), 0.6, 0.10


def _imminence(cand: CandidateTrigger, as_of: date) -> float:
    if cand.event_datetime is None:
        return 0.35                                          # evergreen / news: a flat prior
    days = (cand.event_datetime.date() - as_of).days
    if days < 0:
        return 0.0
    peak = 1.15 if 1 <= days <= 3 else 1.0                  # a small bump in the pre-event window
    return max(0.0, min(1.0, (1.0 - days / _LOOKAHEAD) * peak))


def _novelty(cand: CandidateTrigger, as_of: date) -> float:
    s = coverage.stats(cand, as_of)
    n = 1.0 - min(0.8, 0.2 * s["times_covered"])
    if s["days_since_last"] is not None:
        n -= max(0.0, 1.0 - s["days_since_last"] / 30.0) * 0.4
    return max(0.0, min(1.0, n))


def _persona_cov(cand: CandidateTrigger, recency: dict) -> float:
    d = recency.get(cand.persona)
    return 1.0 if d is None else max(0.2, min(1.0, d / 30.0))


def _evergreen(cand: CandidateTrigger) -> float:
    if cand.source != "standing":
        return 0.0
    p = cand.provenance
    return min(1.0, p.get("evergreen_floor", 0.35) + (0.45 if p.get("hot") else 0.0))


def deterministic_dims(cand: CandidateTrigger, as_of: date, recency: dict) -> dict[str, float]:
    return {
        "imminence": _imminence(cand, as_of),
        "data_readiness": min(1.0, (cand.readiness.salient_count / 10.0) if cand.readiness else 0.0),
        "novelty": _novelty(cand, as_of),
        "persona_coverage": _persona_cov(cand, recency),
        "user_intent": 1.0 if cand.source == "user" else 0.0,
        "evergreen_fit": _evergreen(cand),
    }


class _Judged(BaseModel):
    id: str
    market_impact: float = Field(description="0..1 — how market-moving is the event/theme")
    angle_novelty: float = Field(description="0..1 — freshness of the angle, not just the topic")
    zeitgeist_salience: float = Field(description="0..1 — how live in the current news cycle")


class _JudgedList(BaseModel):
    scores: list[_Judged]


def _llm_judge(cands: list[CandidateTrigger]) -> dict[str, dict]:
    index = [c.index_row() for c in cands]
    try:
        from ..studio.llm import get_llm
        llm = get_llm(max_tokens=2048).with_structured_output(_JudgedList)
        res = llm.invoke(
            "You are the editor scoring candidate article ideas for a market-research desk. Judge every "
            "candidate on its own merits — a jurisdiction is never inherently more market-moving than "
            "another (a Bank of England decision, a euro-area HICP flash and an FOMC decision are all "
            "tier-1; the `jurisdiction` field must not sway market_impact). For EACH candidate below, "
            "rate three dimensions in [0,1]: market_impact (how market-moving the event/theme is — a "
            "central-bank rate decision or a CPI/HICP inflation print is high, a minor housing revision "
            "low), angle_novelty (is the ANGLE fresh, not just the topic), zeitgeist_salience (how live "
            "it is in the current news cycle). Return one row per id.\n\nCANDIDATES:\n" + json.dumps(index))
        return {s.id: {"market_impact": s.market_impact, "angle_novelty": s.angle_novelty,
                       "zeitgeist_salience": s.zeitgeist_salience} for s in res.scores}
    except Exception:
        return {}


def score_all(cands: list[CandidateTrigger], as_of: date) -> list[CandidateTrigger]:
    recency = coverage.persona_recency(as_of)
    judged = _llm_judge([c for c in cands if c.readiness and c.readiness.groundable])
    for c in cands:
        dims = deterministic_dims(c, as_of, recency)
        jb = {d: "det" for d in dims}
        jd = judged.get(c.id, {})
        for d in _JUDGED:
            dims[d] = float(jd.get(d, 0.5)); jb[d] = "llm"
        excluded = "" if (c.readiness and c.readiness.groundable) else "not groundable in the estate"
        base = sum(WEIGHTS[d] * dims.get(d, 0.0) for d in WEIGHTS)
        bonus = _BONUS if sum(dims.get(d, 0) >= _BONUS_AT for d in _BONUS_DIMS) >= 3 else 0.0
        total = -1.0 if excluded else base + bonus
        c.scores = ScoreBreakdown(dims=dims, weights=dict(WEIGHTS), judged_by=jb, base=round(base, 4),
                                  bonus=bonus, total=round(total, 4), excluded_reason=excluded)
    return cands


def shortlist_top(cands: list[CandidateTrigger], k: int = 3) -> list[CandidateTrigger]:
    """Greedy top-k with a same-persona diversity penalty (user candidates are exempt)."""
    pool = sorted([c for c in cands if c.scores and not c.scores.excluded_reason],
                  key=lambda c: c.scores.total, reverse=True)
    picks: list[CandidateTrigger] = []
    used_personas: set[str] = set()
    while pool and len(picks) < k:
        best, best_adj = None, -2.0
        for c in pool:
            adj = c.scores.total
            if c.source != "user" and c.persona in used_personas:
                adj -= 0.15                                  # diversity penalty
            if adj > best_adj:
                best, best_adj = c, adj
        picks.append(best); pool.remove(best); used_personas.add(best.persona)
    return picks
