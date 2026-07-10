# Model Catalog — entry contract (§09 Deliverable 1)

The catalog is the authored source-of-truth for the **decision-maker × model matrix**
(assessment §05), grounded in the model literature review (§11) and the input-state
principle (§10). It is deliberately **model-centric**: because the matrix is many-to-many
(`DecisionMaker M:N Model M:N Decision`, §06), every model is authored **once** and joined
to the personas that use it via `USES` edges. This maps 1:1 onto the Neo4j spine that
Deliverable 4 will seed from these files (shared `Model` nodes; `USES`/`INFORMS` edges as
the join).

Two record types.

---

## 1. Model  — `catalog/models/<model_id>.yaml`

One file per model. Authored once even when many personas use it.

```yaml
model_id:  curve_fair_value           # stable snake_case id; == filename stem
name:      "Curve fair value (OIS)"
family:    rates                       # rates | vol | credit | fx | commodity | equity | macro | event
summary:   "One-line: what the model computes and the gap it reveals."

spec:                                  # from §11; the executable definition, not prose
  form:       "Human/mathematical statement of the model."
  assumptions: ["…", "…"]
  params:                              # named parameters with defaults where known
    daycount: "ACT/360"
  references: ["https://…"]            # §11 citations / corpus paper ids

inputs:                                # §10 STATE TUPLES — an input is a state, not a series
  - ref:    "USD:ois"                  # what to bind (see `source` for how to resolve it)
    source: curve                      # observations | curve | derived | event
    order:  level                      # level | delta | delta2 | context | diffusion | surprise
    window: "1d"                       # observation/lookback window
    horizon: "target_meeting"          # REQUIRED — the forward point the input is read at
    note:   "OIS interpolated to the meeting date."  # optional
  # `source` tells the validator (and later the Executor) WHERE the input lives in UMD:
  #   observations -> ref is a `observations.series_id`            (e.g. "DFF", "CME_SR3_*")
  #                   a trailing "*" makes it a STRIP (LIKE match; passes if >=1 series matches)
  #   curve        -> ref is "<CCY>:<curve_type>" in curve_snapshots (e.g. "USD:ois")
  #   derived      -> ref is a derived series NOT YET materialized  (Deliverable 2 transform stack)
  #   event        -> ref is a Kalshi/event series in observations  (e.g. "KXFED_implied_rate")
  # `order` is the §10 derivative/context order the model consumes that input at.
  # `horizon` is the forward point the input is evaluated at. REQUIRED on every input. Values:
  #   spot          -> as-of now / latest observation (T0)
  #   full_curve    -> the entire term structure is consumed (all tenors/contracts)
  #   <tenor|date>  -> a single forward point (e.g. "21m", "2027-04-fomc", "target_meeting")
  # CRITICAL: any two legs that are COMPARED (e.g. OIS-implied vs prediction-market-implied) MUST
  # carry the SAME horizon. Comparing an OIS front rate to a 2027 implied rate is a category error
  # (the defect that prompted this field). The Executor binds each input at its declared horizon.

outputs:                               # the named numbers the model PRODUCES (the only numbers allowed downstream)
  - name: "fair_value_residual_bp"
    unit: "bp"
    note: "Model curve minus market, per tenor. Sign = rich/cheap."

interpretation: >                      # the `asserts` text the Narrator uses — what the number MEANS
  "This tenor is rich/cheap vs the fitted curve; the gap, not the level, is the trade."

visualizations:                        # FIRST-CLASS. Charts are Horizon3's differentiator (H2's were
                                        # the failure) — every model DECLARES its signature insight-chart(s),
                                        # never an afterthought. Rendered deterministically from `outputs`.
  - id: curve_richcheap                 # stable id (the render bridge keys data by this id)
    form: "bar (per tenor) + fitted-curve line"   # dataviz form(s)
    chart_type: bar                     # CANONICAL renderer key (optional): fan | heatmap | surface3d |
                                        # smile | lines | bar | dumbbell | scatter | stacked_area | table.
                                        # If absent, render/from_catalog infers it from `form`. Maps to a
                                        # render.charts primitive — charts generate straight from this spec.
    encodes: "fair_value_residual_bp by tenor, vs the fitted curve"
    insight: "which tenors are rich/cheap — the RV trade; the gap, not the level"
    color_job: diverging                # sequential | diverging | categorical | status (per dataviz)
    dim: 2D                             # 2D | 3D | table
  # list the decision view + the analyst view + the auditable table where they differ.

implemented_by: "unified_market_data.analysis.curve_builder.build_ois_curve"
  # module.fn in the UMD `analysis/` package that EXECUTES this model.
  # OR, when the model is named in §05/§11 but not yet built:
  # build_stub: true                    # -> becomes a Deliverable-5 build task, NOT app code
  # (a model file has exactly one of `implemented_by` or `build_stub: true`)
```

**Rules**
- The LLM never authors a number — `implemented_by` names the code that does (hard rule #2).
- Every `ref` must resolve against live UMD, or be explicitly `source: derived` (a declared
  Deliverable-2 gap). Never invent a series_id.
- Every input carries an `order` (§10). Encoding only "series → model" is insufficient.

---

## 2. Persona  — `catalog/personas.yaml`

One document, a list of the 11 decision-makers. This is the M:N join.

```yaml
personas:
  - persona_id: macro_rates_trader
    name: "Macro rates trader"
    decision: "Position the duration / swap book ahead of events."
    uses: [curve_fair_value, ois_implied_path, carry_roll_down,
           term_premium_acm, curve_pca, rate_divergence]   # model_ids; a model may be USED by many personas
```

A shared model (e.g. `term_premium_acm`, also used by the central-bank policymaker) appears
in multiple personas' `uses` lists — but its spec lives in exactly one model file. Write the
edge, never a second copy.

---

## Validation

`python scripts/validate_catalog.py` checks, read-only, against the live UMD estate:
1. schema well-formedness (required keys; `order`/`source`/`family` in their enums; exactly
   one of `implemented_by` / `build_stub`);
2. every `source: observations|curve|event` `ref` resolves to real UMD data;
3. every non-stub `implemented_by` resolves to a real callable in UMD `analysis/`;
4. every `personas[].uses` id resolves to a model file.

It prints per-model PASS or the exact missing link, and lists `build_stub` models as the
explicit Deliverable-5 backlog (stubs are expected gaps, not failures). This is the embryo of
the Deliverable-6 conviction test.
