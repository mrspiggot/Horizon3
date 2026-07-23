"""The coverage log — what we've surfaced and published, so novelty can penalise repetition.

Append-only JSONL at output/ats/coverage.jsonl. The read side answers "how recently / how often did we
cover this persona+domain?" (the novelty-vs-recent-coverage signal and the persona-coverage balance);
the write side records each shortlist and each human pick (the pick weighs more heavily).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .schema import CandidateTrigger

_LOG = Path(__file__).resolve().parents[2] / "output" / "ats" / "coverage.jsonl"


def _load() -> list[dict]:
    if not _LOG.exists():
        return []
    rows = []
    for line in _LOG.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _append(row: dict) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _key(persona: str, domain: str | None) -> str:
    return f"{persona}|{domain or ''}"


def stats(cand: CandidateTrigger, as_of: date) -> dict:
    """{times_covered, days_since_last} for this candidate's persona+domain (picks weigh double)."""
    rows = _load()
    k = _key(cand.persona, cand.domain)
    hits = [r for r in rows if _key(r.get("persona", ""), r.get("domain")) == k]
    times = sum(2 if r.get("kind") == "pick" else 1 for r in hits)
    days = None
    for r in sorted(hits, key=lambda r: r.get("date", ""), reverse=True):
        try:
            days = (as_of - date.fromisoformat(r["date"])).days
            break
        except Exception:
            continue
    return {"times_covered": times, "days_since_last": days}


def persona_recency(as_of: date) -> dict[str, int | None]:
    """{persona: days_since_last_covered or None} — for the persona-coverage balance dimension."""
    rows = _load()
    out: dict[str, int | None] = {}
    for r in rows:
        p = r.get("persona", "")
        try:
            d = (as_of - date.fromisoformat(r["date"])).days
        except Exception:
            continue
        if p and (out.get(p) is None or d < out[p]):
            out[p] = d
    return out


def record_shortlist(cands: list[CandidateTrigger], as_of: date) -> None:
    for c in cands:
        _append({"kind": "shortlist", "date": as_of.isoformat(), "candidate_id": c.id,
                 "persona": c.persona, "domain": c.domain, "source": c.source, "title": c.title})


def record_pick(cand: CandidateTrigger, as_of: date, article_path: str) -> None:
    _append({"kind": "pick", "date": as_of.isoformat(), "candidate_id": cand.id,
             "persona": cand.persona, "domain": cand.domain, "source": cand.source,
             "title": cand.title, "article_path": article_path})
