# docs/system — architecture documentation for the agentic subsystem

Two things live here:

| File | What it is | Owned by |
|------|------------|----------|
| `agentic-system-design.html` | The **hand-crafted showcase** design doc (the published Artifact's source), kept as the v0 baseline. | human |
| `agentic-system-design.generated.html` / `.md` | The **living** doc, regenerated from live code + the Neo4j spine. Diagrams, tables and counts are always current. | `render/sysdoc/` |
| `system_manifest.json` | The **machine-truth manifest** the living doc is rendered from, and the baseline the drift-gate compares against. | `render/sysdoc/` |

## Regenerate the living doc

```bash
~/venv/bin/python scripts/gen_sysdoc.py            # full build (live Neo4j census)
~/venv/bin/python scripts/gen_sysdoc.py --no-spine # code-only (skip Neo4j)
~/venv/bin/python scripts/gen_sysdoc.py --snapshot # also snapshot to snapshots/<sha>/
```

## Keep it honest (drift-gate)

The generator separates **machine-truth** (auto-extracted: the LangGraph DAGs via
`get_graph()`, the Neo4j spine census, an AST read of the prompts) from **narrative**
(hand-owned markdown in `render/sysdoc/narrative/`, which the generator never
overwrites). The drift-gate fails when the code's architecture diverges from the
committed manifest:

```bash
~/venv/bin/python scripts/check_sysdoc_drift.py                  # exit 1 on drift
~/venv/bin/python scripts/check_sysdoc_drift.py --include-spine  # also compare the census
~/venv/bin/python scripts/check_sysdoc_drift.py --changelog OLD.json NEW.json
```

On drift: run `gen_sysdoc.py` and commit the regenerated `system_manifest.json` (+ docs).
The spine census is excluded from the gate by default — data freshness is not code drift.

## Design notes

- Only 4 of the 5 components are LangGraph `StateGraph`s (`article_graph`, `selector`,
  `studio`, `judge`); the **ATS is a hand-coded orchestrator**, modelled from
  `render/sysdoc/annotations.yaml` (not auto-drawn).
- `get_llm()` ignores `temperature` at runtime (Opus 4.8); the catalogue labels temps
  as *declared*, not applied.
- The live GraphRAG is the **Neo4j spine**; the ChromaDB corpus is design-time only.
