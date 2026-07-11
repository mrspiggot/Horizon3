# The model-knowledge graph — ontology & contract

This is the machine-usable contract for the executable, renderable model corpus (assessment §06,
§01). A **model** is authored once as an enriched YAML spec (`catalog/models/<id>.yaml`); the spec is
**loaded into Neo4j** as the graph below, and the same spec drives the **Executor** (runs the model)
and the **graph-driven renderer** (turns outputs into insight charts). YAML is the human-editable
source of truth; the graph is the queryable, app-facing serialization. Both deserialize to one
in-memory `ModelSpec`, so "the Python interprets the graph to run models and render insights" holds.

The chain the graph must carry (the owner's directive):
**Model → inputs (as §10 states) → outputs → interpretations of outputs → charts that summarise the insight.**

## Acceptance floors (validator-enforced hard gate)
- **≥ 3 models per persona.**
- **Each model ≥ 3 inputs** — distinct input *variables* (each read as a §10 state via `state_tuple`).
- **Each model ≥ 4 charts**, each tied to an `interpretation` (the count + linkage is machine-checked;
  "insightful" is the human's call, hard-rule #1).
- **Each model ≥ 1 `grounded_in` paper**, present in `knowledge/registry.yaml` and ingested.

## Graph nodes & edges (loaded into horizon-neo4j, namespace `catalog:'horizon3'`)

```
(DecisionMaker{persona})-[:MAKES]->(Decision{what})
(DecisionMaker)-[:USES]->(Model{id,name,family})-[:INFORMS]->(Decision)
(Model)-[:HAS_SPEC]->(ModelSpecification{equations,assumptions,params})
(Model)-[:GROUNDED_IN]->(Paper{id,title,authors,url,tier})          // from the knowledge corpus
(Model)-[:TAKES_INPUT]->(ModelInput{id,role,source,transform,state,window,horizon})
(ModelInput)-[:BOUND_TO]->(DataSeries{series_id})                    // raw-series inputs
(Model)-[:IMPLEMENTED_BY]->(ImplementationFunction{ref})            // module.fn in UMD analysis/
(Model)-[:PRODUCES]->(ModelOutput{name,unit,meaning})
(ModelOutput)-[:INTERPRETED_AS]->(Interpretation{id,when,says})
(Interpretation)-[:ILLUSTRATED_BY]->(Chart{id,chart_type,color_job,insight,data_contract})
(Chart)-[:ENCODES]->(ModelOutput)
(Model)-[:GENERIC_OVER]->(Axis)-[:HAS_INSTANCE]->(Instance)          // the generalisation dimension
```

## Authored spec — `catalog/models/<id>.yaml`

```yaml
model_id: <id>
name: "<human name>"
family: rates|vol|credit|fx|commodity|equity|macro|event
grounded_in: [<paper_id>, ...]        # REQUIRED (floor) — ids in knowledge/registry.yaml
generic_over: [<axis>]                 # currency|underlying|event|commodity|pair|issuer|equity
jurisdictions|instances: [<id>, ...]   # where it instantiates

spec:
  equations: "<the actual math, from the paper>"
  assumptions: ["..."]
  params: {<name>: <value>}            # model constants (r*, target, weights, recovery, ...)

inputs:                                # ≥3 distinct variables (floor)
  - id: <input_id>
    role: <role>                       # bound per-instance via the axis file (jurisdictions.yaml, ...)
    source: series | derived           # raw DataSeries, or computed (transform/sub-model)
    transform: none|yoy|log|<fn>       # how the modelled quantity is derived from the raw series
    state: level|direction|acceleration|zscore|percentile   # which §10 component the model consumes
    window: "<e.g. 12m>"
    horizon: <e.g. latest|1y|spot>
    # source: derived inputs carry `compute:` — a UMD fn + its own input ids (e.g. output_gap)

execution:                             # the exec binding: resolved input states -> impl kwargs
  implemented_by: <module.fn>          # a REAL, import-clean UMD analysis/ callable
  args: {<impl_param>: <input_id>.<state> | <const>}   # e.g. inflation_pct: cpi.level

outputs:                               # ModelOutput[] — the single source of every number
  - {name: <name>, unit: "<unit>", meaning: "<what it means>"}

interpretations:                       # Interpretation[] — the reading of outputs
  - id: <interp_id>
    when: "<condition over outputs/inputs, e.g. policy.level < taylor_1993 - 0.5>"
    says: "<the insight in words>"

charts:                                # Chart[] — ≥4 (floor), each tied to an interpretation
  - id: <chart_id>
    chart_type: fan|heatmap|surface3d|smile|lines|bar|dumbbell|scatter|stacked_area|table
    interpretation: <interp_id>
    color_job: sequential|diverging|categorical
    insight: "<what the chart reveals>"
    data_contract:                     # machine-readable: how outputs/series map to the chart's data dict
      kind: named_values|series|matrix|xy|stacked
      # e.g. named_values -> {labels:[...], values:[<output names>]}
      #      xy            -> {x:<output/series>, y:<output/series>, labels:<...>}
      #      series        -> {x:<series>, series:[{label,from}], band:<...>}
```

## The three execution contracts (what the Python does with the graph)

1. **Input resolution → state.** For each `ModelInput`: if `source: series`, resolve `role` → the
   instance's `DataSeries` (axis binding) → pull history via `MarketDataAPI.get_history`, apply
   `transform`, then `state_tuple(...)`. If `source: derived`, run its `compute:` fn on its own inputs
   first. Bad/implausible data is **refused at this boundary** (§04-fm3), never clipped.
2. **Execution → outputs.** Bind `execution.args` (each `input_id.state` or a constant) to the
   `implemented_by` callable's kwargs, run it (NON-LLM), and persist each result as a `ModelOutput`
   value in `model_run` / `model_output_point`. The LLM authors nothing here.
3. **Interpretation → chart.** Evaluate each `interpretation.when` over the outputs/inputs; for each
   `Chart`, assemble its `data_contract` from the `ModelOutput` values (+ any encoded series) and hand
   the shaped dict to `render/charts.py` via the graph-driven renderer. Charts render **outputs**, not
   raw series (§06) — never a tautology.

## Faithfulness
Where an external published anchor exists, the model's implementation is validated against it
(e.g. a built Financial Conditions Index vs the official `NFCI`; the ACM identity `ACMY=ACMTP+ACMRNY`).
Every output carries provenance (series_id / source / units / horizon). "Done" is a human judging the
rendered insight-charts, never a green gate.
