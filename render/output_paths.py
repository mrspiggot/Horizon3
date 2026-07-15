"""Canonical output layout — everything a run produces lives under output/<date>/.

    output/<YYYY-MM-DD>/
      briefing.html            the ATS morning briefing (all shortlisted cards)
      briefs/<slug>/           a shortlisted STUB: infographic + charts + gist + card
      articles/<slug>/         a fully rendered ARTICLE: article.docx + illustration + infographic + charts
      index.json …             ATS run metadata (index/scores/picks)

So there is ONE obvious place to find both the generated stubs and the full rendered articles for
any given day. Older un-dated output (output/articles/<persona>, output/skeleton_articles,
output/ats/<date>) is left where it is; new runs use this scheme.

Usage:
    from render.output_paths import article_dir, brief_dir, run_root
    out = article_dir("volatility_trader")            # output/2026-07-15/articles/volatility_trader/
    out = brief_dir(candidate.id, as_of=as_of_date)   # output/<as_of>/briefs/<id>/
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output"


def _slug(s) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(s)).strip("-") or "item"


def _day(as_of: date | str | None) -> str:
    if as_of is None:
        return date.today().isoformat()
    return as_of.isoformat() if isinstance(as_of, date) else str(as_of)[:10]


def run_root(as_of: date | str | None = None) -> Path:
    """The dated root for a run: output/<YYYY-MM-DD>/ (created)."""
    p = OUTPUT_ROOT / _day(as_of)
    p.mkdir(parents=True, exist_ok=True)
    return p


def article_dir(slug, as_of: date | str | None = None) -> Path:
    """Home for one fully rendered article: output/<date>/articles/<slug>/ (created)."""
    p = run_root(as_of) / "articles" / _slug(slug)
    p.mkdir(parents=True, exist_ok=True)
    return p


def brief_dir(slug, as_of: date | str | None = None) -> Path:
    """Home for one shortlisted stub/brief: output/<date>/briefs/<slug>/ (created)."""
    p = run_root(as_of) / "briefs" / _slug(slug)
    p.mkdir(parents=True, exist_ok=True)
    return p
