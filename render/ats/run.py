"""The ATS orchestrator — harvest → map → readiness-gate → score → shortlist → briefing → record.

One entry point, `run_ats(as_of, conn, out_dir, ...)`. Read-only except the outputs it writes under
`out_dir` (the briefing, the candidate index, the scores, a picks map) and the coverage log. The LLM is
touched at most twice (the mapper's classifier for free-text triggers, and one scoring call); everything
else is deterministic.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from . import briefing, coverage, mapper, readiness, score, shortlist, vocab
from .harvest import HarvestContext, harvest_all
from .schema import Shortlist


def _load_fred_key() -> str:
    if os.environ.get("FRED_API_KEY"):
        return os.environ["FRED_API_KEY"]
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    except Exception:
        pass
    return os.environ.get("FRED_API_KEY", "")


def _upcoming_meetings(as_of: date, lookahead: int) -> list[dict]:
    try:
        sys.path.insert(0, str(Path.home() / "PycharmProjects" / "unified_market_data" / "src"))
        from unified_market_data.analysis.cb_meeting_calendars import meetings_for
    except Exception:
        return []
    out, horizon = [], as_of + timedelta(days=max(lookahead, 30))
    for j in vocab.jurisdictions():
        for d in meetings_for(j["ccy"]):
            d = d.date() if hasattr(d, "date") else d
            if as_of <= d <= horizon:
                out.append({"jur": j["id"], "ccy": j["ccy"], "cb": j["central_bank"], "date": d})
    return out


def _recent_surprises(conn, as_of: date) -> list[dict]:
    dom = {"CPI": "inflation", "PCE": "inflation", "NFP": "growth", "GDP": "growth"}
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_type, surprise, event_date FROM macro_events "
                    "WHERE event_date >= %s ORDER BY event_date DESC LIMIT 40",
                    (as_of - timedelta(days=10),))
        rows = cur.fetchall(); cur.close()
    except Exception:
        return []
    out = []
    for et, surprise, ed in rows:
        d = ed.date() if hasattr(ed, "date") else ed
        out.append({"domain": dom.get((et or "").upper().split()[0], None),
                    "z": float(surprise or 0.0), "date": d, "event_type": et})
    return [s for s in out if s["domain"]]


def run_ats(as_of: date, conn, out_dir, *, user_input: str = "", lookahead_days: int = 12,
            backend: str = "auto", make_cards: bool = True) -> Shortlist:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = HarvestContext(as_of=as_of, lookahead_days=lookahead_days, user_input=user_input,
                         upcoming_meetings=_upcoming_meetings(as_of, lookahead_days),
                         recent_surprises=_recent_surprises(conn, as_of), fred_key=_load_fred_key())

    cands = harvest_all(ctx)
    cands = mapper.map_all(cands)
    cands = list({c.id: c for c in cands}.values())          # dedup by id
    cands = readiness.gate(cands, conn)
    cands = score.score_all(cands, as_of)
    picks = score.shortlist_top(cands, k=3)

    sl = Shortlist(as_of=as_of.isoformat(), picks=picks, all_candidates=cands)
    if make_cards:
        sl.cards = shortlist.build_cards(picks, conn, out_dir, backend=backend)
        sl.briefing_path = briefing.render_briefing(sl, out_dir / "briefing.html", as_of)

    # audit trails
    (out_dir / "index.json").write_text(json.dumps([c.index_row() for c in cands], indent=2))
    (out_dir / "scores.json").write_text(json.dumps(
        [{"id": c.id, "title": c.title, "source": c.source, "persona": c.persona,
          **(asdict(c.scores) if c.scores else {})} for c in
         sorted(cands, key=lambda c: (c.scores.total if c.scores else -9), reverse=True)], indent=2))
    (out_dir / "picks.json").write_text(json.dumps(
        {c.id: {"persona": c.persona, "title": c.title, "source": c.source,
                "jurisdiction": c.jurisdiction or (c.readiness.jurisdiction if c.readiness else "")}
         for c in picks}, indent=2))
    coverage.record_shortlist(picks, as_of)
    return sl
