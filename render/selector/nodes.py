"""Model-Selection nodes: library (Neo4j) → propose (LLM) → validate (deterministic).

§06 role 2. The same division of labour the Judge uses, for the same reason:

    the LLM PROPOSES   — "which models inform a treasurer's decision to term out debt?" is a
                         judgement about meaning. It needs to know that funding_cost and real_funding
                         answer different halves of that question, and that copper_gold_growth speaks
                         to the growth backdrop the decision sits in. No query expresses that.

    THE GRAPH DISPOSES — a model is offerable only if it is PROVEN executable: it RAN, and the node
                         carries the run_id and point count. The LLM cannot select a model that does
                         not exist, cannot run, or has no data — because it is never offered one.

That constraint is the whole safety property. The old spine held 38 models of which 35 could not
execute; an unconstrained selector over that graph would confidently pick `curve_pca` and the engine
would raise FileNotFoundError. Here the library IS the executable set, by construction.
"""
from __future__ import annotations

import os
import sys

from neo4j import GraphDatabase

from ..studio.llm import get_llm
from .state import Picks, SelectState

REASONING_MODEL = "claude-opus-4-8"
CATALOG = "horizon3"


_ARRAY_NUDGE = ("\n\nIMPORTANT — FORMAT: return `picks` as a JSON ARRAY of objects, each with string "
                "fields `model_id` and `why`. Do NOT encode the array, or any field, as a single quoted "
                "string; emit real JSON structure.")


def _invoke(llm, prompt: str, tries: int = 4):
    """Retry the known `.with_structured_output` flake, where the model serialises the nested `picks`
    list as a STRING and pydantic rejects it. The reasoning model runs at a FIXED temperature (Opus 4.8
    deprecates the knob, and get_llm is cached), so a plain re-ask reproduces the identical bad
    serialisation — which is exactly why this ValidationError 'recurred' every run instead of clearing.
    Nudge the PROMPT harder toward a well-formed array each try; changing the input is what actually
    changes a deterministic model's output."""
    last = None
    for i in range(tries):
        try:
            return llm.invoke(prompt + _ARRAY_NUDGE * i)
        except Exception as exc:                            # ValidationError / parse error → re-ask, firmer
            last = exc
    raise last


def driver():
    return GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7688"),
                                auth=(os.getenv("NEO4J_USERNAME", "neo4j"),
                                      os.getenv("NEO4J_PASSWORD", "devpassword")))


def load_library(_state: SelectState) -> dict:
    """Every PROVEN executable model in the spine — the closed vocabulary selection may draw on.

    Nothing here is a claim: `executable` was written by seed_spine.py only after the model ran, and
    `points`/`as_of` are that run's evidence. A model with no proof is not in the library.
    """
    d = driver()
    try:
        with d.session() as s:
            rows = s.run(
                """MATCH (m:Model {catalog:$cat, executable:true})
                   OPTIONAL MATCH (m)-[:PRODUCES]->(o:Output)
                   OPTIONAL MATCH (m)-[:RENDERS]->(v:Visualization)
                   RETURN m.id AS id, m.name AS name, m.family AS family, m.method AS method,
                          m.points AS points, m.as_of AS as_of,
                          collect(DISTINCT o.name + ' (' + coalesce(o.unit,'') + ') — ' +
                                  coalesce(o.meaning,'')) AS outputs,
                          collect(DISTINCT v.insight) AS insights
                   ORDER BY m.id""", cat=CATALOG).data()
    finally:
        d.close()
    if not rows:
        # An empty library means the spine was never seeded, and a selector that silently returns
        # nothing would look exactly like "no model fits". Say it.
        print("SPINE EMPTY — no proven executable models. Run scripts/seed_spine.py.", file=sys.stderr)
    return {"library": rows}


_PROPOSE = """You are the MODEL-SELECTION step for a financial article. A decision-maker is about to
be written about. Your job: choose which executable models they should RUN to reach their decision.

THE DECISION-MAKER
  {persona}: {decision}

THE LIBRARY — every model that is PROVEN to execute on real data (it was run; the point count and
last observation are the proof). You may ONLY choose from these ids, exactly:

{library}

CURRENTLY HARDCODED for this persona: {defaults}
Those are a FLOOR, not a ceiling, and they are not sacred — they were typed into a YAML file by hand.
Include them if they serve the decision. Reach beyond them when another model in the library speaks
to the same decision: the whole point of this step is that a decision-maker may use ANY model that
informs their decision, not just the few someone once listed.

RULES
- Choose {min_models}-{max_models} models. Fewer than {min_models} makes a thin article; more than
  {max_models} makes an unfocused one.
- SCOPE DISCIPLINE. The floor is your default set; you may add AT MOST {add_budget} models beyond it,
  so spend them well. Do NOT add a model that merely decomposes, re-cuts, or offers a second view of a
  concept a floor model already carries — a spread model plus a second model that decomposes the SAME
  spread is one idea shown twice, not two readings. That exact over-reach (importing an extra
  decomposition an article did not need) is what broke the last batch. A model earns an addition only
  by bringing a reading the floor cannot show at all.
- Choose for the DECISION, not for topical adjacency. A commodity analyst forecasting growth and
  inflation is served by a copper/gold growth signal even though it is not "a commodity model"; a
  volatility trader is not served by a labour-market model merely because both are macro.
- Every pick needs a `why` that names what THIS model tells THIS decision-maker about THIS decision.
  If you cannot write that sentence, do not pick the model. "It provides useful context" means you
  have not got one.
- Prefer models whose outputs actually disagree or interact — an article is an argument, and the
  argument needs at least two readings that can conflict. A set that all says the same thing is one
  model with extra steps.
- Never invent an id. If nothing in the library fits, return fewer picks and say so in the `why` of
  the ones you did choose.

{feedback}"""


def propose(state: SelectState) -> dict:
    lib = "\n".join(
        f"  {m['id']}  ({m['family']}) — {m['name']}\n"
        f"      executed: {m['points']} points → {m['as_of']}\n"
        f"      method: {(m.get('method') or '')[:180]}\n"
        f"      outputs: {'; '.join(x for x in (m.get('outputs') or []) if x)[:220]}"
        for m in state["library"])
    fb = state.get("feedback") or ""
    prompt = _PROPOSE.format(
        persona=state["persona_id"], decision=state["decision"], library=lib,
        defaults=", ".join(state["default_models"]),
        min_models=state.get("min_models", 3), max_models=state.get("max_models", 5),
        add_budget=state.get("add_budget", 2),
        feedback=(f"YOUR LAST ATTEMPT WAS REJECTED: {fb}\nFix it.\n" if fb else ""))

    llm = get_llm(model=REASONING_MODEL).with_structured_output(Picks)
    got: Picks = _invoke(llm, prompt)
    return {"picks": got.picks, "iterations": state.get("iterations", 0) + 1}


def validate(state: SelectState) -> dict:
    """Deterministic. The LLM's judgement about relevance stands; its claims about what exists do not."""
    offerable = {m["id"] for m in state["library"]}
    selected, reasons, rejected = [], {}, []
    for p in state.get("picks") or []:
        if p.model_id not in offerable:
            rejected.append(f"{p.model_id!r} is not a proven executable model")
            continue
        if p.model_id in reasons:
            continue                                   # a duplicate pick is not two models
        selected.append(p.model_id)
        reasons[p.model_id] = p.why

    # SCOPE BUDGET (P2b). Bias to the proven floor: keep every floor model the LLM selected, then admit
    # additions only up to `add_budget`. This is what stops a regeneration sprawling four models deep —
    # the credit/labour/cost pieces regressed by importing 3 extra decompositions; here they keep at most
    # two. Enforced deterministically so the ceiling holds even when the prompt rule is ignored.
    lo, hi = state.get("min_models", 3), state.get("max_models", 5)
    add_budget = state.get("add_budget", 2)
    floor = set(state.get("default_models") or [])
    kept_floor = [m for m in selected if m in floor]
    additions = [m for m in selected if m not in floor]
    if len(additions) > add_budget:
        rejected.append(f"scope budget: {len(additions)} additions beyond the floor trimmed to "
                        f"{add_budget} (bias to the proven core)")
        additions = additions[:add_budget]
    selected = (kept_floor + additions)[:hi]
    if len(selected) > hi:
        selected, rejected = selected[:hi], rejected + [f"capped at {hi} (picked {len(selected)})"]
    if len(selected) < lo:
        rejected.append(f"only {len(selected)} valid picks — need at least {lo}")
    reasons = {m: reasons[m] for m in selected if m in reasons}

    # THE FLOOR. A selector that returns nothing usable must not silently produce an article with no
    # models: the planner did exactly that on 2026-07-16 (offered 13 charts, shipped 1) and the net
    # only caught zero. Fall back to what the persona already had, loudly.
    if not selected:
        print(f"SELECTION FAILED — {state['persona_id']}: falling back to the hardcoded models "
              f"({', '.join(state['default_models'])}). {'; '.join(rejected)}", file=sys.stderr)
        selected = list(state["default_models"])
        reasons = {m: "hardcoded default — selection produced nothing usable" for m in selected}
    return {"selected": selected, "reasons": reasons, "rejected": rejected,
            "feedback": "; ".join(rejected[:4]) if rejected else ""}
