# START HERE — warm-start prompt for a Claude Code session

`CLAUDE.md` is auto-loaded into every session, so the context below is already
present. Use this file when you want to *explicitly* orient a session on the next
piece of work — paste the block as your first message, editing the "TASK" line.

---

```
Before anything else, read and internalise:
- CLAUDE.md (this repo) — the charter and the seven hard rules.
- ~/PycharmProjects/Horizon2/docs/assessment/ — the full assessment. At minimum
  §00 (recommendation), §04 (failure post-mortem), §05 (decision-maker × model
  matrix), §06 (target architecture), §09 (roadmap), §10 (input-state principle),
  §11 (model literature), §12 (SoTA agentic/prompting).
- knowledge/ — the living corpus. Query it to ground any foundational claim:
  `~/venv/bin/python -m knowledge.search "<topic>"`. Do not design from memory.

Context you must hold:
- Horizon3 is the successor to Horizon2 (kept only as a learning template of what
  went wrong — do NOT extend it). It is a model→data→insight→decision engine on top
  of the salvaged UMD data platform (~/PycharmProjects/unified_market_data).
- We are in the FOUNDATION phase. Only the knowledge corpus exists. NO app engine
  is built until the UMD data layers are proven generic (assessment §09): the
  decision-maker × model matrix, a normalized time-series taxonomy + derivative
  stack, a relational model-config/run store, and the Neo4j model spine — proven by
  a conviction test where every persona traces cleanly through the three layers.
- Non-negotiable rules: the LLM never authors a number (numbers come from executing
  catalogued models); rendering is deterministic code (no diffusion for numeric
  artifacts); every input is a state (level + 1st/2nd derivative + context), not a
  level; bad data is refused not masked; prove things across the FULL remit, never
  just FOMC; "done" means a human looked at the output and it is good, not that a
  gate passed; prove one excellent artifact before systematizing.
- Consume UMD via its MarketDataAPI seam / SQL (TimescaleDB localhost:5434) / Cypher
  (horizon-neo4j Bolt localhost:7688). Never re-implement pricing or re-ingest data.
  Check ~/.claude/rules/devctl.md before assigning any port/DB.

TASK: <state the specific next task here — e.g. "author the decision-maker × model
matrix as YAML seeds for the Neo4j model spine, per assessment §05/§06">

Work data-layer-first, ground each decision in the corpus, and show me a real,
looked-at artifact — not a plan for a system.
```
