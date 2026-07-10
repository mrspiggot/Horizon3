---
name: corpus
description: Ground a design decision in the Horizon3 living knowledge corpus (foundational papers on agentic architecture, prompting/context engineering, data-faithful visualization, and economic models). Use when the user asks to check the literature, cite a principle, see what the corpus holds, add a paper, or run corpus curation.
---

# Corpus skill

The living knowledge corpus lives in `knowledge/` and is the design-time grounding
for Horizon3 (and the future runtime literature-RAG). Always ground foundational
claims in it rather than from memory — that discipline is why it exists.

## Search the corpus (most common)
Run, from the repo root with the shared venv:
```
~/venv/bin/python -m knowledge.search "the topic or claim to ground" -k 5
```
Report the returned papers (id, title, url) and the relevant excerpt. If nothing
returns, the collection may need building: `~/venv/bin/python -m knowledge.ingest`.

## See what is tracked / held
- Curated papers: `knowledge/registry.yaml` (tiers: canonical / reference / candidate).
- Watched topics + arXiv queries: `knowledge/topics.yaml`.
- Physical copies: `knowledge/sources/`.

## Add a paper (human-curated)
1. Download the PDF into `knowledge/sources/` (arXiv: `https://arxiv.org/pdf/<id>`).
2. Add a `canonical` entry to `knowledge/registry.yaml` (id, title, url, arxiv_id,
   local_path, topics, why). Mark any superseded paper with `superseded_by`.
3. Re-run `~/venv/bin/python -m knowledge.ingest`.

## Discover new papers (never auto-adopt)
```
~/venv/bin/python -m knowledge.curate --dry-run    # report only
~/venv/bin/python -m knowledge.curate              # write candidates + digest
```
`curate.py` only ever writes to `knowledge/candidates.yaml` + a dated digest under
`knowledge/digests/` and notifies — it NEVER promotes to canonical. A human reviews
the digest and promotes by editing `registry.yaml`. This runs twice weekly via
`scripts/curate.sh` (cron `0 9 * * 0,3`).
