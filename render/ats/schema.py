"""The ATS contract — the candidate an editor weighs, and the score that justifies surfacing it.

A `CandidateTrigger` is a proposed article: where it came from, what it's about, when it matters, which
persona/model would ground it, and (once probed) whether our estate can actually ground it. The scorer
sees only the COMPACT projection (`CandidateTrigger.index_row`) — never raw feeds — and every surfaced
card carries a full `ScoreBreakdown` so the human sees exactly why it made the shortlist.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

Source = str  # "calendar" | "zeitgeist" | "user" | "standing"


@dataclass
class ReadinessResult:
    """Can our estate ground this candidate NOW? (the firewall corollary — no numbers, no article).

    `jurisdiction` is the jurisdiction we PROBED — the candidate's own for a jurisdiction-bound trigger,
    or (for a jurisdiction-agnostic one) the best-grounded jurisdiction we found. Never a US default.
    """
    groundable: bool
    persona: str = ""
    jurisdiction: str = ""
    salient_count: int = 0
    n_numbers: int = 0
    as_of: str = ""
    note: str = ""


@dataclass
class ScoreBreakdown:
    dims: dict[str, float] = field(default_factory=dict)     # each normalised to [0,1]
    weights: dict[str, float] = field(default_factory=dict)
    judged_by: dict[str, str] = field(default_factory=dict)  # dim -> "det" | "llm"
    base: float = 0.0
    bonus: float = 0.0
    total: float = 0.0
    excluded_reason: str = ""                                # non-empty ⇒ dropped before ranking


@dataclass
class CandidateTrigger:
    source: Source
    title: str
    rationale: str = ""                                      # the "why now" one-liner
    event_datetime: datetime | None = None                  # the anchoring moment; None ⇒ evergreen/news
    jurisdiction: str | None = None                         # e.g. "US" (catalog/jurisdictions.yaml)
    domain: str | None = None                               # events.yaml vocab: rates/inflation/growth/crypto
    personas: list[str] = field(default_factory=list)       # filled by the mapper (⊆ the 8 graph personas)
    models: list[str] = field(default_factory=list)
    raw_refs: list[str] = field(default_factory=list)       # urls / series ids / event keys (provenance)
    provenance: dict = field(default_factory=dict)          # {harvester, fetched_at, ...}
    readiness: ReadinessResult | None = None
    scores: ScoreBreakdown | None = None

    @property
    def id(self) -> str:
        key = f"{self.source}|{self.title}|{self.event_datetime}"
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    @property
    def persona(self) -> str:
        """The persona the article will actually be grounded on (the first mapped one)."""
        return self.personas[0] if self.personas else ""

    def index_row(self) -> dict:
        """The COMPACT projection the LLM scorer sees — never raw feeds (index-then-load, §12)."""
        return {
            "id": self.id, "source": self.source, "title": self.title, "rationale": self.rationale,
            "event_datetime": self.event_datetime.isoformat() if self.event_datetime else None,
            "jurisdiction": self.jurisdiction, "domain": self.domain, "persona": self.persona,
            "grounded_jurisdiction": self.readiness.jurisdiction if self.readiness else "",
            "groundable": bool(self.readiness and self.readiness.groundable),
            "salient_count": self.readiness.salient_count if self.readiness else 0,
        }


@dataclass
class Shortlist:
    as_of: str
    picks: list[CandidateTrigger] = field(default_factory=list)   # the top-3 (with cards)
    all_candidates: list[CandidateTrigger] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)              # build_article output per pick
    briefing_path: str = ""
