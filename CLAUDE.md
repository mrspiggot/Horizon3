# Horizon3 — project charter & session warm-start

**Read this first.** It is the durable context for any Claude Code session in this
repo, so you never cold-start. Owner: Richard Walker (Lucidate Ltd).

## What Horizon3 is

The successor application to **Horizon2**, rebuilt natively as a **model → data →
insight → decision** engine on top of the salvaged **UMD** data platform. Horizon2
is kept, read-only, as the *learning template of what went wrong* — do not extend
it.

The differentiator is **insight**, not charts. Insight = **the output of running
the relevant decision-maker's model against real, multi-dimensional data, told as
that model would tell it.** Every decision-maker (central banker, macro/RV rates
trader, treasurer, credit/FX/commodity/equity/vol/event trader, forecaster) runs a
*model* on *data* to reach a *decision*; the chart, infographic, and prose are
three *renderings* of that model output.

## Where the thinking lives (read before building)

- **The assessment** (13 docs + master): `docs/assessment/` (this repo — it is
  Horizon3's founding rationale; a point-in-time copy also exists in Horizon2's
  history as its own post-mortem record).
  §00 recommendation, §04 the failure post-mortem, §05 decision-maker × model
  matrix, §06 target architecture, §09 roadmap, §10 the input-*state* principle,
  §11 the model literature review, §12 SoTA agentic/prompting/context-engineering.
- **The living knowledge corpus**: `knowledge/` (this repo). Physical copies of the
  foundational papers + a vector store. Query it while designing:
  `python -m knowledge.search "your topic"`. It is the design-time grounding and
  the future runtime literature-RAG. Keep using it — do not design from memory.

## Hard rules (learned the hard way from Horizon2 — non-negotiable)

1. **"Done" = a human looked at the output and it is good.** Gates are aids, never
   the definition of success. Look at every artifact. (Horizon2 shipped garbage
   charts under green gates and a validation box that lied — the
   `dishonest_validation_panel`.)
2. **The LLM never authors a number.** Numbers come from *executing* a catalogued
   model on data; the LLM selects, designs, and narrates only. Naming a model
   without running it is worthless.
3. **Rendering is deterministic code.** No diffusion image model touches a numeric
   artifact (charts, infographics). Verified numbers → structured spec → code →
   render (Infogen/LIDA/chart-to-code). Horizon2's infographic used gpt-image and
   was unreliable by construction.
4. **Every input is a state, not a level** — level, first derivative
   (direction/speed), second derivative (acceleration), and context. This is
   universal, not an inflation quirk (assessment §10).
5. **Bad data is refused at the boundary, never masked/clipped-and-shipped.**
6. **Generic, not FOMC.** Prove things across the full decision-maker matrix. FOMC
   is one row, never the yardstick — the recurring Horizon2 failure.
7. **Prove one excellent artifact before systematizing.** Taste precedes
   architecture. Don't answer "the output is bad" with "here's a bigger system."
8. **Determinism for facts, agents for judgment.** A regex/keyword blocklist must
   NEVER make an editorial or taste judgment (decisive-vs-shrug, AI-slop, tone) — a
   regex cannot read meaning (it convicted the decisive "one reading of where policy
   stands" as a hedge and dropped the infographic). That call belongs to an LLM
   editor/critic. Deterministic code is for FACTS (number == fmt(data-val),
   provenance, structure, template/token leaks) and RETRIEVAL (text→chart) ONLY —
   never agentify those (rule #2). Every new LLM judge fails OPEN and must be PROVEN
   to fire (a known-bad input flags, a known-good passes) — a silently-failing-open
   judge is a green gate that lies (the `dishonest_validation_panel` again).

## Sequencing (the gate)

**No app engine is built until the UMD data layers are proven generic** (assessment
§09): the decision-maker × model matrix authored; the time-series taxonomy
normalized + a derivative/transform stack; a relational model-config/run store; the
Neo4j **model spine** seeded; and every persona traces cleanly
`decision → model → inputs → execution → outputs → relationships`. Today only the
knowledge corpus exists — that is intentional.

## The data seam (how Horizon3 reaches UMD)

UMD (`~/PycharmProjects/unified_market_data`) is the data platform: TimescaleDB
(`localhost:5434`, `unified_market_data`), a relational side (model outputs), and
Neo4j (`horizon-neo4j`, Bolt `localhost:7688`). Consume it via its `MarketDataAPI`
seam / SQL / Cypher — never re-implement pricing or re-ingest data here (UMD is the
single source of truth). Machine conventions live in `~/.claude/rules/devctl.md`
(ports, DBs, Neo4j) — always check devctl before assigning any port/DB.

## Repo conventions

- Python via the shared venv `~/venv` (has chromadb, pymupdf, pyyaml, requests).
- ChromaDB at `~/.chromadb`, corpus collection `knowledge_corpus`.
- Twice-weekly corpus curation: `scripts/curate.sh` (cron `0 9 * * 0,3`).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Push over SSH (`git@github.com:mrspiggot/Horizon3.git`); the `gh` API token is
  currently stale but SSH works.

## Current status

**Foundation phase.** Only `knowledge/` (the living corpus) exists. Next work is
UMD data-layer fitness (assessment §09) — data-layer only, no app code — before any
engine or article generation.
