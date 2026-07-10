"""Ingest the curated corpus into the ChromaDB `knowledge_corpus` collection.

Reuses the chunk/embed/upsert pattern from Horizon2/scripts/ingest_research.py
and the idempotent re-ingest + expiry idea from HorizonCorpus's vector_ingest.py:
each paper's chunks are keyed by paper id, deleted before re-upsert, and a paper
marked `superseded_by` is removed from the index entirely.

Physical copies (canonical, `local_path` PDFs) are extracted with PyMuPDF.
Reference-tier entries without a PDF are indexed from a cached text extract at
`sources/<id>.txt` if present, else skipped with a warning.

Run:  python -m knowledge.ingest [--rebuild]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("horizon3.knowledge.ingest")

ROOT = Path(__file__).resolve().parent
COLLECTION = "knowledge_corpus"
CHUNK_SIZE = 500   # words (~tokens * 1.3), matches the other Lucidate corpora
CHUNK_OVERLAP = 50


def load_registry() -> list[dict]:
    data = yaml.safe_load((ROOT / "registry.yaml").read_text())
    return data.get("papers", []) if data else []


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + size]))
        start += size - overlap
    return chunks


def extract_pdf(path: Path) -> str:
    import pymupdf
    doc = pymupdf.open(str(path))
    parts = [doc[i].get_text().strip() for i in range(len(doc))]
    doc.close()
    return "\n".join(p for p in parts if p)


def source_text(paper: dict) -> str | None:
    """The best available text for a paper: its PDF, else a cached extract."""
    lp = paper.get("local_path")
    if lp and (ROOT / lp).exists():
        try:
            return extract_pdf(ROOT / lp)
        except Exception as e:
            logger.warning("PDF extract failed for %s: %s", paper["id"], e)
    cached = ROOT / "sources" / f"{paper['id']}.txt"
    if cached.exists():
        return cached.read_text(errors="ignore")
    return None


def get_collection():
    from chromadb import PersistentClient
    client = PersistentClient(path=str(Path.home() / ".chromadb"))
    return client.get_or_create_collection(COLLECTION)


def _delete_paper(collection, paper_id: str) -> None:
    try:
        collection.delete(where={"paper_id": paper_id})
    except Exception as e:
        logger.debug("delete %s: %s", paper_id, e)


def ingest_paper(paper: dict, collection) -> int:
    pid = paper["id"]
    _delete_paper(collection, pid)  # idempotent re-ingest
    if paper.get("superseded_by"):
        logger.info("retired %s (superseded_by %s) — removed from index", pid, paper["superseded_by"])
        return 0
    if paper.get("tier") == "candidate":
        return 0  # candidates are watchlist-only until a human promotes them
    text = source_text(paper)
    if not text:
        logger.warning("no source text for %s (%s) — skipped; add a PDF or sources/%s.txt",
                       pid, paper.get("tier"), pid)
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    ids, docs, metas = [], [], []
    for i, ch in enumerate(chunks):
        ids.append(hashlib.md5(f"{pid}:c{i}".encode()).hexdigest())
        docs.append(ch)
        metas.append({
            "paper_id": pid, "title": paper.get("title", ""), "tier": paper.get("tier", ""),
            "topics": ",".join(paper.get("topics", [])), "url": paper.get("url", ""),
            "chunk_index": i,
        })
    collection.upsert(documents=docs, ids=ids, metadatas=metas)
    logger.info("ingested %s: %d chunks", pid, len(chunks))
    return len(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest the knowledge corpus into ChromaDB")
    ap.add_argument("--rebuild", action="store_true", help="delete the collection first")
    args = ap.parse_args()

    collection = get_collection()
    if args.rebuild:
        from chromadb import PersistentClient
        PersistentClient(path=str(Path.home() / ".chromadb")).delete_collection(COLLECTION)
        collection = get_collection()
        logger.info("rebuilt collection %s", COLLECTION)

    papers = load_registry()
    total = sum(ingest_paper(p, collection) for p in papers)
    indexed = sum(1 for p in papers
                  if p.get("tier") in ("canonical", "reference") and not p.get("superseded_by"))
    logger.info("done: %d chunks across %d indexed papers; collection now holds %d chunks",
                total, indexed, collection.count())
    return 0


if __name__ == "__main__":
    sys.exit(main())
