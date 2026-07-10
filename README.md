# Horizon3

The successor application to Horizon2, built natively as a **model → data →
insight → decision** engine on top of the salvaged **UMD** data platform. Horizon2
remains, read-only, as the documented learning template (see
`Horizon2/docs/assessment/`).

**Status:** foundation phase. The application engine is **not** built yet — it is
gated behind the UMD data-layer fitness work (assessment §09). The first and only
subsystem here today is the **living knowledge corpus**, which grounds the design
in current best practice before any app code is written.

## Living knowledge corpus (`knowledge/`)

Curated, versioned copies of the foundational papers that drive our principles —
SoTA agentic architecture, prompting / context engineering, and the economic
models — plus a twice-weekly utility that surfaces newly-published or replacement
papers for human review, and a vector store to query it all.

| File | Role |
|---|---|
| `knowledge/registry.yaml` | The curated corpus: one entry per paper (canonical / reference / candidate), with provenance and *why it matters*. |
| `knowledge/topics.yaml` | Tracked concepts + the arXiv queries that watch them + their current canonical papers. |
| `knowledge/sources/` | Physical local copies (PDF / text) — defeats link-rot. |
| `knowledge/ingest.py` | Chunk → embed → upsert the corpus into the ChromaDB `knowledge_corpus` collection. |
| `knowledge/curate.py` | Twice-weekly: query the arXiv API per topic, rank, write **candidates** + a review digest, notify. **Never auto-promotes.** |
| `knowledge/search.py` | Query the corpus (design-time grounding; later runtime literature-RAG). |
| `scripts/curate.sh` | Cron wrapper (`0 9 * * 0,3` — Sun & Wed 09:00). |

### Curation discipline (how we avoid drift)
Automation **discovers**; a human **curates**. `curate.py` only ever writes
`candidate` rows and a digest. A human promotes a candidate to `canonical` (or
marks an older paper `superseded_by`) by editing `registry.yaml`, then re-runs
`ingest.py`. Canonical papers keep a physical copy in `sources/`.

## Usage
```bash
# build/refresh the vector store from the registry
python -m knowledge.ingest
# query it
python -m knowledge.search "model-grounded generation"
# discover new papers for review (writes candidates + digest; promotes nothing)
python -m knowledge.curate --dry-run
```

## Conventions
- Sibling project under `~/PycharmProjects`, consuming UMD via its API seam
  (later). ChromaDB at `~/.chromadb`, collection `knowledge_corpus`, shared
  default embedder (consistent with the other Lucidate corpora).
- devctl registration (path, `neo4j_consumes: horizon-neo4j`, a UI port) is added
  when the application UI exists — deferred; the corpus subsystem needs no port.
