"""Model-Selection — §06 role 2, as a bounded LangGraph agent.

    library → propose → validate → END
                 ▲          │
                 └─(rejected)┘   (bounded by max_iterations)

§06: "Model-Selection (LLM, against the Neo4j catalog)". It is the last of the seven roles to exist.

WHAT IT REPLACES. `catalog/graph/personas.yaml` hardcodes a model list per persona — 4 for the
central banker, 2 for the commodity analyst — typed by hand and never revisited. That is why we have
28 US-shaped scripts rather than the "near-limitless library of real models" §01 describes: the
library exists, and each persona can only see the handful someone listed for it. commodity_analyst is
bound to 2 models and wrote the thinnest article in the 2026-07-17 batch — 3 measured figures in 1,743
words — while 26 other proven models sat in the graph it could not reach.

WHY IT IS SAFE. The library is drawn from the spine's PROVEN executable set: seed_spine.py writes
`executable:true` only after running the model, and stores the run_id. So the LLM chooses among
models that demonstrably execute on real data today. It cannot pick a model that does not exist
(validate rejects it), cannot pick one that cannot run (never offered), and cannot return nothing
(falls back to the hardcoded list, loudly).

The hardcoded list stays in the YAML as the floor. This role decides the ceiling.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import SelectState


def _after_validate(state: SelectState) -> str:
    # A rejected pick (an id that is not a proven model, too few, too many) is the SELECTOR's failure,
    # not the catalog's. Re-propose with the reason; never ship a set nobody checked.
    if state.get("rejected") and state.get("iterations", 0) < state.get("max_iterations", 2):
        return "propose"
    return END


def build_graph():
    g = StateGraph(SelectState)
    g.add_node("library", nodes.load_library)
    g.add_node("propose", nodes.propose)
    g.add_node("validate", nodes.validate)
    g.add_edge(START, "library")
    g.add_edge("library", "propose")
    g.add_edge("propose", "validate")
    g.add_conditional_edges("validate", _after_validate, {"propose": "propose", END: END})
    return g.compile()


def select_models(persona_id: str, decision: str, default_models: list[str], *,
                  min_models: int = 3, max_models: int = 6, max_iterations: int = 2) -> dict:
    """Choose the models this decision-maker should run. Returns {selected, reasons, rejected}.

    `default_models` is personas.yaml's hardcoded list — the floor if selection produces nothing.
    """
    return build_graph().invoke(
        {"persona_id": persona_id, "decision": decision, "default_models": default_models,
         "min_models": min_models, "max_models": max_models, "max_iterations": max_iterations,
         "iterations": 0, "feedback": ""},
        config={"recursion_limit": 12},
    )
