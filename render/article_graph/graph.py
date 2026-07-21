"""The article StateGraph — §06's model→data→insight→decision pipeline as one traced graph.

    material → brief → plan → draft → reconcile_charts → illustrate → reconcile_dashboard → assemble

`draft` is the atomic best-of-N redraft loop (write → ground → critique → keep-best) kept as one
cohesive node; its iterations show as LLM spans in LangSmith. The two `reconcile_*` nodes are the
consistency stage the pipeline never had — they bind charts to the sections that read them, build the
charts the prose names, and derive the dashboard from the finished article. Shape mirrors the judge,
selector and studio graphs already in this repo.
"""
from __future__ import annotations

import os
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import ArticleState

_ORDER = ["material", "brief", "plan", "draft",
          "reconcile_charts", "illustrate", "reconcile_dashboard", "assemble"]


def build_graph():
    g = StateGraph(ArticleState)
    for name in _ORDER:
        g.add_node(name, getattr(nodes, name))
    g.add_edge(START, _ORDER[0])
    for a, b in zip(_ORDER, _ORDER[1:]):
        g.add_edge(a, b)
    g.add_edge(_ORDER[-1], END)
    return g.compile()


def run_article(persona_id: str, conn, out_dir, *, jurisdiction: str, backend: str = "auto",
                max_iter: int = 3, model_ids: list | None = None) -> dict:
    """Compile and invoke the article graph for one (decision-maker, currency); returns the final
    ArticleState. `jurisdiction` is REQUIRED and runs the models in that currency (US is a peer, never a
    hidden default); `model_ids` pins an explicit set (the graph enumerator's pick) over Role-2."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LANGSMITH_PROJECT"] = os.environ.get("HORIZON3_LANGSMITH_PROJECT", "horizon3-article")
    return build_graph().invoke(
        {"persona_id": persona_id, "conn": conn, "out_dir": str(out_dir),
         "backend": backend, "max_iter": max_iter, "jurisdiction": jurisdiction, "model_ids": model_ids},
        config={"recursion_limit": 24, "run_name": f"article:{persona_id}:{jurisdiction}",
                "metadata": {"persona": persona_id, "jurisdiction": jurisdiction, "component": "article_graph"}},
    )
