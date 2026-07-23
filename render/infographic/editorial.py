"""Agentic editorial review of infographic reader-copy — the JUDGMENT the deterministic gate must not own.

The tier-1 gate (``gate.py``) verifies FACTS deterministically: every figure equals ``fmt(data-val)``,
traces to an executed model output, no number sits in the illustration slot. That is correct as code —
you verify numbers by inspection, never by asking an LLM.

Whether the PROSE commits to a view or shrugs is a different thing entirely: an editorial judgment that
depends on meaning in context. It was implemented as a 25-word regex blocklist (``gate._HEDGE``), which
convicted the decisive line *"Four published models, one reading of where policy stands"* — a single,
unified verdict — as a hedge, because a regex cannot read. In an agentic app the judgment belongs to a
model that reads the line the way an editor would.

This module is that judge. It reads the headline / deck / thesis / read copy with the persona's decision
as context, flags GENUINE equivocation (hedging between alternatives, refusing to commit), and rewrites
only the offending line — decisively, carrying the same meaning, and touching NO number or ``{placeholder}``
(that is the deterministic firewall's domain, and it re-runs afterwards as the backstop).

Fail-OPEN by construction: if the model is unreachable, or ``HORIZON3_NO_EDITORIAL`` is set, the copy
ships unrevised. An LLM outage must never block a render — the numbers are already guaranteed correct by
the deterministic gate, and shipping a curated persona line unrevised is far better than exploding.
"""
from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field

from .schema import InfographicSpec

# A line we refuse to hand to the rewriter: it carries a number or an unfilled {placeholder}. Wording is
# the LLM's job; numbers are the firewall's. Never let the two cross.
_NUMISH = re.compile(r"[{}]|\d")
_EDITABLE_BLOCKS = {"thesis_callout", "note"}   # the pure-prose reader surfaces (plus title/deck)
_TITLE, _DECK = "__title__", "__deck__"


class _LineVerdict(BaseModel):
    id: str
    decisive: bool = Field(description="True if the line commits to a view; False if it equivocates / shrugs")
    issue: str = Field(default="", description="the specific hedge, or empty if decisive")
    revision: str = Field(default="", description="a decisive rewrite with the SAME meaning and NO number/placeholder; empty if already decisive")


class _Review(BaseModel):
    lines: list[_LineVerdict]


def _reader_lines(spec: InfographicSpec) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if spec.title.strip():
        out.append((_TITLE, spec.title))
    if spec.deck.strip():
        out.append((_DECK, spec.deck))
    for b in spec.blocks:
        if b.type in _EDITABLE_BLOCKS and (b.text or "").strip():
            out.append((b.id, b.text))
    return out


def _apply(spec: InfographicSpec, lid: str, text: str) -> None:
    if lid == _TITLE:
        spec.title = text
    elif lid == _DECK:
        spec.deck = text
    else:
        for b in spec.blocks:
            if b.id == lid:
                b.text = text
                return


_PROMPT = (
    "You are the editor of a markets publication held to an FT / Economist standard. Your house style is "
    "decisive: every reader-facing line must COMMIT to a view. Judge the lines below.\n\n"
    "Decisive = states a single, committed conclusion. Note carefully: a line is decisive even if it "
    "contains the words 'one reading', 'the read', 'a take' etc. when it means ONE unified verdict — e.g. "
    "\"Four published models, one reading of where policy stands\" is DECISIVE (the models converge on a "
    "single verdict). Do NOT flag that.\n"
    "Equivocation (flag it) = hedging BETWEEN alternatives or refusing to commit: 'by one reading X, by "
    "another Y', 'it may be that', 'on balance perhaps', 'arguably', 'hard to say', 'time will tell', "
    "'some would argue'. The test is meaning, not any single word.\n\n"
    "For each line that genuinely equivocates, write `revision`: a decisive rewrite that keeps the SAME "
    "factual meaning and register, and introduces NO number, %, or {{placeholder}}. Leave `revision` empty "
    "for decisive lines.\n\n"
    "Persona: {persona}\nDecision the piece supports: {decision}\n\nLINES:\n{lines}"
)


def review_and_repair(spec: InfographicSpec, *, max_fix: int = 3) -> InfographicSpec:
    """Judge the reader copy with an LLM editor and decisively rewrite any genuine shrug. Numbers and
    placeholders are never touched. Fails open — returns the spec unchanged on any error."""
    if os.environ.get("HORIZON3_NO_EDITORIAL"):
        return spec
    lines = _reader_lines(spec)
    if not lines:
        return spec
    try:
        from ..studio.llm import get_llm
        llm = get_llm(max_tokens=1200).with_structured_output(_Review)
        rendered = "\n".join(f"  [{lid}] {text}" for lid, text in lines)
        review = llm.invoke(_PROMPT.format(persona=spec.persona, decision=spec.deck or "—", lines=rendered))
    except Exception:
        return spec                                      # fail open — the deterministic gate still guards facts
    verdicts = {v.id: v for v in review.lines}
    fixes = 0
    for lid, original in lines:
        v = verdicts.get(lid)
        if not v or v.decisive or not v.revision.strip():
            continue
        # never let the LLM rewrite a line that carries a number/placeholder — that is the firewall's domain
        if _NUMISH.search(original) or _NUMISH.search(v.revision):
            continue
        _apply(spec, lid, v.revision.strip())
        fixes += 1
        if fixes >= max_fix:
            break
    return spec


class _Contradiction(BaseModel):
    contradicted_ids: list[str] = Field(
        default_factory=list,
        description="ids whose stated direction/level the ARTICLE BODY plainly contradicts for the SAME concept")


def contradicted_by_body(body: str, items: list[tuple[str, str]]) -> set[str]:
    """Which data-derived state badges does the finished article BODY plainly contradict?

    `items` = [(id, "CPI: elevated, rising"), …]. A dashboard must never state the opposite of the prose
    beside it (the Horizon2 'dishonest panel'). Deciding whether prose contradicts a state is meaning, not
    a keyword — it was a set of direction-word regexes (_FALLING/_RISING/…) that fired on "not falling"
    and missed paraphrase. An LLM reads the body and each badge's claim and returns only GENUINE
    contradictions (badge says rising, body says that concept is falling).

    Fails OPEN → set() (suppress nothing). The badges are computed from data and TRUE; on an LLM outage it
    is better to show the data than to over-suppress it, and the caller's floor still holds.
    """
    if not body or not items or os.environ.get("HORIZON3_NO_EDITORIAL"):
        return set()
    try:
        from ..studio.llm import get_llm
        llm = get_llm(max_tokens=600).with_structured_output(_Contradiction)
        listing = "\n".join(f"  [{i}] {claim}" for i, claim in items)
        res = llm.invoke(
            "You are fact-checking an infographic against its own article. Each badge states a "
            "data-derived STATE for one concept (level and/or momentum, e.g. 'CPI: elevated, rising'). "
            "Return ONLY the ids whose direction or level the ARTICLE BODY plainly contradicts FOR THE "
            "SAME concept — the body says that concept is falling where the badge says rising, or low "
            "where the badge says elevated. Do not flag silence, a different concept, or a fuzzy read.\n\n"
            "BADGES:\n" + listing + "\n\nARTICLE BODY:\n" + body[:6000])
        valid = {i for i, _ in items}
        return {i for i in res.contradicted_ids if i in valid}
    except Exception:
        return set()
