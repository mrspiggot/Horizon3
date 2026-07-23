"""ATS morning briefing — propose the day's shortlist, or write the one the owner picks.

    # produce today's briefing (3 shortlisted articles as skeleton cards):
    ~/venv/bin/python scripts/ats_briefing.py --as-of 2026-07-14
    # add an owner commission (a paragraph and/or URLs):
    ~/venv/bin/python scripts/ats_briefing.py --user "the dollar's slide and what it means for EM credit"
    # publish the chosen candidate as a full ~1200-word article:
    ~/venv/bin/python scripts/ats_briefing.py --as-of 2026-07-14 --pick <candidate_id>

Trigger proposes, human disposes — the full writer runs only on an explicit --pick.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.ats import run as ats_run          # noqa: E402
from render.ats import coverage                # noqa: E402
from render.output_paths import run_root, article_dir  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _conn():
    return psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")


def _pick(as_of: date, cand_id: str, backend: str) -> None:
    picks_path = run_root(as_of) / "picks.json"
    if not picks_path.exists():
        print(f"no shortlist for {as_of} — run without --pick first"); return
    picks = json.loads(picks_path.read_text())
    if cand_id not in picks:
        print(f"{cand_id} not in {as_of}'s shortlist ({', '.join(picks)})"); return
    persona = picks[cand_id]["persona"]
    jurisdiction = picks[cand_id].get("jurisdiction")         # the candidate's OWN jurisdiction — never a US default
    if not jurisdiction:
        print(f"{cand_id} has no jurisdiction recorded — re-run the shortlist to refresh picks.json")
        return
    from render.writer import build_article_full
    conn = _conn()
    out = article_dir(cand_id, as_of)   # output/<date>/articles/<cand_id>/
    print(f"writing full article: {persona} [{jurisdiction}] → {out}")
    r = build_article_full(persona, conn, out, jurisdiction=jurisdiction, backend=backend)
    print(f"PASS  {r['words']}w  {r['sections']}sec  critic_ok={r['critic_ok']}  → {r['docx_path']}")
    # reconstruct a minimal candidate for the coverage record
    from render.ats.schema import CandidateTrigger
    c = CandidateTrigger(source=picks[cand_id]["source"], title=picks[cand_id]["title"], personas=[persona])
    coverage.record_pick(c, as_of, r["docx_path"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--user", default="", help="owner commission: a paragraph and/or URLs")
    ap.add_argument("--lookahead", type=int, default=12)
    ap.add_argument("--backend", default="auto")
    ap.add_argument("--pick", default="", help="candidate id to publish as a full article")
    ap.add_argument("--email", action="store_true", help="email the briefing PDF (needs SMTP_* in .env)")
    ap.add_argument("--to", default="", help="override recipient (default SMTP_TO / owner)")
    a = ap.parse_args()
    as_of = date.fromisoformat(a.as_of)

    if a.pick:
        _pick(as_of, a.pick, a.backend)
        return

    conn = _conn()
    out_dir = run_root(as_of)           # output/<date>/ — briefing + briefs/ + metadata
    sl = ats_run.run_ats(as_of, conn, out_dir, user_input=a.user, lookahead_days=a.lookahead,
                         backend=a.backend)
    print(f"\n{len(sl.cards)}/{len(sl.all_candidates)} shortlisted for {as_of}:")
    for c in sl.picks:
        s = c.scores.total if c.scores else 0
        print(f"  [{c.id}] {s:.2f}  {c.source:9} {c.persona:26} “{c.title[:64]}”")
    print(f"\nbriefing → {sl.briefing_path}")
    if a.email:
        from render.ats import email
        email.send_briefing(sl, sl.briefing_path, as_of, to=a.to)
    print(f"to publish one:  scripts/ats_briefing.py --as-of {as_of} --pick <id>")


if __name__ == "__main__":
    main()
