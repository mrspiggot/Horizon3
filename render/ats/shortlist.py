"""Render each shortlisted candidate as a skeleton card — the reuse point.

Each of the top-3 is rendered with `render/article.py::build_article` (the exact skeleton the build phase
adopted: a Van Gogh header + the persona's infographic + charts + a 150-200-word firewall-guarded gist).
The card bundles that with the candidate's score breakdown and "why now" for the briefing.
"""
from __future__ import annotations

from pathlib import Path

from ..article import build_article
from .schema import CandidateTrigger


def build_cards(picks: list[CandidateTrigger], conn, out_dir: Path, *, backend: str = "auto") -> list[dict]:
    cards = []
    for c in picks:
        art, err = {}, ""
        # Render the card in the candidate's OWN jurisdiction (hard-rule #6) — its own for a
        # jurisdiction-bound trigger, else the jurisdiction readiness found groundable. Never a US default:
        # a groundable pick always carries one, so no literal fallback is needed.
        instance = c.jurisdiction or (c.readiness.jurisdiction if c.readiness else "")
        kw = {"instance": instance} if instance else {}
        try:
            art = build_article(c.persona, conn, out_dir / "briefs" / c.id, backend=backend, **kw)
        except Exception as exc:
            err = str(exc).splitlines()[0][:140]
        cards.append({"candidate": c, "article": art, "error": err})
    return cards
