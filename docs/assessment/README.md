# Horizon2 / UMD — Assessment & Recommendation

**Date:** 2026-07-10 · **Author:** engineering assessment for Richard Walker (Lucidate Ltd)

A comprehensive assessment of the Horizon2 application and the UMD data platform,
culminating in the **salvage-vs-rewrite recommendation**. Every finding is grounded
in live audits of the three databases and a component inventory of ~88,000 LOC.

## The recommendation (one line)

> **Salvage the data platform (UMD) in full and extend it; do not patch Horizon2 —
> build a new application on the salvaged data layer, and keep Horizon2 as the
> documented "learning template of what went wrong."** Verdict: **salvage the
> foundation, restart the house.** See `00` and `08`.

## The document set

| # | Document | What it establishes |
|---|---|---|
| 00 | Executive Summary & Recommendation | The verdict, up front, with the decision at a glance |
| 01 | The Vision | model→data→insight→decision; the research blueprint |
| 02 | Current-State Architecture | What exists today (Horizon2 + UMD), honestly |
| 03 | Data-Layer Audit | Live findings across TimescaleDB / relational / Neo4j |
| 04 | Failure Post-Mortem | What went wrong, and the root causes (the learning template) |
| 05 | Decision-maker × Model Matrix | The generic yardstick (11 personas, full remit) |
| 06 | Target Architecture | The generic engine + the three data-layer target schemas |
| 07 | Gap Analysis | Present vs required, per layer; additive vs architectural |
| 08 | Salvage vs Rewrite | Component inventory, scored paths, the decision |
| 09 | Roadmap | The recommended path, data-layer-first, with the conviction gate |
| 10 | Model Input Representation | Why every input is a *state* (level, derivatives, context), not a level — corrects the naïve "inflation only" reading |
| 11 | Model Reference (literature review) | The accepted models per decision-maker: form, inputs, outputs, what they assert, interpretation, references |
| 12 | Agentic Architecture & Prompting | SoTA agentic patterns, context engineering, and the prompting discipline that keeps numbers grounded |

## Formats

- **`docx/MASTER-full-assessment.docx`** — all documents in one file (start here).
- **`docx/NN-*.docx`** — each document individually.
- **`NN-*.md`** — Markdown sources (with Mermaid diagrams).
- Rebuild: `./build.sh` (requires `mmdc` + `pandoc`, both present on this machine).

## Reading order

`00` for the decision; `03`, `04`, `07`, `08` for the evidence behind it; `05`,
`06`, `09` for the target and the path.
