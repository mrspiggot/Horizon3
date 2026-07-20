"""Article-graph node bodies — thin wrappers over the pipeline stages in render/writer.py.

Each node reads the shared ArticleState and returns the fields it produces. The stages themselves
(draft_best, reconcile_charts, make_illustration, reconcile_dashboard, assemble) hold the logic and
are imported from the writer, so the graph is a faithful re-expression of the proven pipeline — not a
reimplementation.
"""
from __future__ import annotations

from pathlib import Path

from .. import writer as W
from ..infographic.from_persona import persona_material


def material(state: dict) -> dict:
    return {"mat": persona_material(state["persona_id"], state["conn"])}


def brief(state: dict) -> dict:
    return {"brief": W.build_brief(state["mat"], conn=state["conn"])}


def plan(state: dict) -> dict:
    return {"outline": W.plan_arc(state["brief"])}


def draft(state: dict) -> dict:
    d = W.draft_best(state["persona_id"], state["brief"], state["outline"], state["conn"],
                     max_iter=state.get("max_iter", 3))
    return {"draft": d}


def reconcile_charts(state: dict) -> dict:
    out = W.reconcile_charts(state["brief"], state["outline"], state["draft"], state["conn"], state["mat"])
    d = dict(state["draft"])
    d["reasons"] = out["reasons"]
    return {"draft": d, "bindings": out["bindings"]}


def illustrate(state: dict) -> dict:
    ill_png, ill_meta = W.make_illustration(state["mat"], state["persona_id"],
                                            Path(state["out_dir"]), state.get("backend", "auto"))
    return {"ill_png": ill_png, "ill_meta": ill_meta}


def reconcile_dashboard(state: dict) -> dict:
    out = W.reconcile_dashboard(state["persona_id"], state["conn"], state["draft"],
                                state["brief"], Path(state["out_dir"]))
    d = dict(state["draft"])
    d["reasons"] = out["reasons"]
    return {"draft": d, "infog_png": out["infog_png"], "cited_keys": out["cited_keys"]}


def assemble(state: dict) -> dict:
    result = W.assemble(state["persona_id"], state["mat"], state["brief"], state["draft"],
                        state["ill_png"], state["ill_meta"], state.get("infog_png"),
                        Path(state["out_dir"]), conn=state["conn"])
    return {"result": result}
