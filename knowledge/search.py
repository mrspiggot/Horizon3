"""Query the knowledge corpus.

Design-time grounding now; the app's runtime literature-RAG later
(assessment §12). Mirrors the query shape of
Horizon2/horizon2/nodes/fetch_data.py::_search_*.

Run:  python -m knowledge.search "model-grounded generation" [-k 5]
"""

from __future__ import annotations

import argparse
from pathlib import Path

COLLECTION = "knowledge_corpus"


def search(query: str, top_k: int = 5) -> list[dict]:
    """Return the top-k corpus chunks for a query (fail-open to [])."""
    try:
        from chromadb import PersistentClient
        client = PersistentClient(path=str(Path.home() / ".chromadb"))
        col = client.get_collection(COLLECTION)
        res = col.query(query_texts=[query], n_results=top_k)
    except Exception:
        return []
    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    for i, doc in enumerate(docs):
        m = metas[i] if i < len(metas) else {}
        out.append({
            "paper_id": m.get("paper_id", ""), "title": m.get("title", ""),
            "url": m.get("url", ""), "tier": m.get("tier", ""),
            "excerpt": (doc or "")[:500],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Query the knowledge corpus")
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()
    hits = search(args.query, args.k)
    if not hits:
        print("(no results — is the corpus ingested? run: python -m knowledge.ingest)")
        return 0
    for h in hits:
        print(f"\n• [{h['paper_id']}] {h['title']}  ({h['tier']})")
        print(f"  {h['url']}")
        print(f"  …{h['excerpt'][:240].strip()}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
