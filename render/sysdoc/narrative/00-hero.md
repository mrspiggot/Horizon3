# An engine where the LLM never authors a number

*Internal design document · model → data → insight → decision*

Horizon3 turns a decision-maker's *model*, run on real market data, into an article,
its charts, and its infographic — three renderings of one executed result. The
intelligence is agentic; the numbers are not. This document maps the LangGraph graphs,
the GraphRAG model spine that feeds them, and the prompts that steer them.

*The diagrams, tables, and counts below are generated from live code and the Neo4j
spine by `render/sysdoc/`; the prose is hand-owned.*
