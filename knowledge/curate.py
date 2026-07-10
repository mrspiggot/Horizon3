"""Twice-weekly corpus curation — DISCOVER, don't decide.

For each tracked topic (topics.yaml) this queries the arXiv API for recent papers,
drops anything already curated (registry.yaml) or already surfaced, and writes the
new hits to:
  - knowledge/candidates.yaml   (machine-owned watchlist; NEVER the human registry)
  - knowledge/digests/candidates-<date>.md   (a review digest)
and sends a notification. It NEVER promotes a paper to canonical and NEVER edits
registry.yaml. A human reviews the digest and, to adopt a paper, adds a canonical
entry to registry.yaml (marking any superseded paper), then re-runs ingest.

Run:  python -m knowledge.curate [--dry-run] [--max N] [--since YYYY-MM-DD]
Cron: 0 9 * * 0,3  (Sun + Wed 09:00) via scripts/curate.sh
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from knowledge.notify import notify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("horizon3.knowledge.curate")

ROOT = Path(__file__).resolve().parent
ARXIV_API = "https://export.arxiv.org/api/query"  # https avoids the 301 redirect
ARXIV_DELAY_S = 3.0   # arXiv etiquette: >= 3s between requests
ARXIV_BACKOFF_S = 20  # on 429, wait this long and retry once
STATE = ROOT / ".curate_state.json"
CANDIDATES = ROOT / "candidates.yaml"
NS = {"a": "http://www.w3.org/2005/Atom"}


def _load_yaml(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    return (data or {}).get(key, []) if isinstance(data, dict) else []


def known_arxiv_ids() -> set[str]:
    ids = set()
    for coll, key in ((ROOT / "registry.yaml", "papers"), (CANDIDATES, "candidates")):
        for p in _load_yaml(coll, key):
            if p.get("arxiv_id"):
                ids.add(str(p["arxiv_id"]).split("v")[0])
    return ids


def arxiv_search(query: str, max_results: int = 10) -> list[dict]:
    """Recent arXiv papers for a query (newest first). Fail-open to []."""
    params = {"search_query": f"all:{query}", "start": 0, "max_results": max_results,
              "sortBy": "submittedDate", "sortOrder": "descending"}
    for attempt in (1, 2):
        time.sleep(ARXIV_DELAY_S if attempt == 1 else ARXIV_BACKOFF_S)
        try:
            r = requests.get(ARXIV_API, params=params, timeout=25)
            if r.status_code == 429 and attempt == 1:
                logger.info("arXiv 429 (%s) — backing off %ds", query[:30], ARXIV_BACKOFF_S)
                continue
            r.raise_for_status()
            root = ET.fromstring(r.text)
            break
        except Exception as e:
            if attempt == 2:
                logger.warning("arXiv query failed (%s): %s", query[:40], e)
                return []
    else:
        return []
    out = []
    for e in root.findall("a:entry", NS):
        raw_id = (e.findtext("a:id", "", NS) or "").rsplit("/", 1)[-1]
        out.append({
            "arxiv_id": raw_id.split("v")[0],
            "title": " ".join((e.findtext("a:title", "", NS) or "").split()),
            "published": (e.findtext("a:published", "", NS) or "")[:10],
            "url": e.findtext("a:id", "", NS),
            "summary": " ".join((e.findtext("a:summary", "", NS) or "").split())[:400],
        })
    return out


def curate(dry_run: bool = False, max_per_query: int = 10, since: str | None = None) -> dict:
    topics = _load_yaml(ROOT / "topics.yaml", "topics")
    known = known_arxiv_ids()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_by_topic: dict[str, list[dict]] = {}
    seen_now: set[str] = set()
    for t in topics:
        tid = t["id"]
        floor = since or t.get("watch_since", "2000-01-01")
        hits: list[dict] = []
        for q in t.get("queries", []):
            for p in arxiv_search(q, max_per_query):
                aid = p["arxiv_id"]
                if aid in known or aid in seen_now:
                    continue
                if p["published"] < floor:
                    continue
                seen_now.add(aid)
                p["topic"] = tid
                hits.append(p)
        if hits:
            new_by_topic[tid] = sorted(hits, key=lambda x: x["published"], reverse=True)

    total = sum(len(v) for v in new_by_topic.values())

    # write the review digest
    if total and not dry_run:
        lines = [f"# Corpus candidates — {today}\n",
                 f"{total} new arXiv paper(s) across {len(new_by_topic)} topic(s). "
                 "Review; to adopt, add a canonical entry to registry.yaml and re-run ingest.\n"]
        cand_rows = []
        for tid, hits in new_by_topic.items():
            lines.append(f"\n## {tid}\n")
            for h in hits:
                lines.append(f"- **{h['title']}** ({h['published']}) — arXiv:{h['arxiv_id']}\n"
                             f"  {h['url']}\n  {h['summary'][:220]}…")
                cand_rows.append({
                    "id": f"cand-{h['arxiv_id']}", "title": h["title"], "url": h["url"],
                    "arxiv_id": h["arxiv_id"], "topics": [tid], "tier": "candidate",
                    "added": today, "why": "auto-surfaced; pending human review",
                    "superseded_by": None,
                })
        (ROOT / "digests").mkdir(exist_ok=True)
        (ROOT / "digests" / f"candidates-{today}.md").write_text("\n".join(lines))
        # append to the machine-owned candidates watchlist (dedup)
        existing = _load_yaml(CANDIDATES, "candidates")
        existing_ids = {c["arxiv_id"] for c in existing if c.get("arxiv_id")}
        merged = existing + [c for c in cand_rows if c["arxiv_id"] not in existing_ids]
        CANDIDATES.write_text(yaml.safe_dump({"candidates": merged}, sort_keys=False))
        state["last_run"] = today
        STATE.write_text(json.dumps(state))

    subject = f"Corpus curation: {total} new candidate(s) across {len(new_by_topic)} topic(s)"
    logger.info(subject + (" [dry-run]" if dry_run else ""))
    if total and not dry_run:
        notify(subject, f"See knowledge/digests/candidates-{today}.md", level="info", email=True)
    return {"total": total, "by_topic": {k: len(v) for k, v in new_by_topic.items()}, "dry_run": dry_run}


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover new corpus papers (human curates)")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--max", type=int, default=10, help="max results per query")
    ap.add_argument("--since", help="override floor date YYYY-MM-DD")
    args = ap.parse_args()
    res = curate(dry_run=args.dry_run, max_per_query=args.max, since=args.since)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
