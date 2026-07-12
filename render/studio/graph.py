"""The Chart Studio agent graph — insight → best chart.

    framer → proposer → critic_panel → compile → multimodal_critique
                                          ▲             │
                                          │        (defects?) ── reviser ──┘
                                          │             │ (clean)
                                          └──(judge fails)── judge ──(ships)──▶ END

Both loops are bounded by `iterations` (incremented at each compile) < `max_iterations`, so the
graph always terminates. Every step is traced to LangSmith (see llm._load_env).
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import nodes
from .insight import InsightBrief
from .state import StudioState


def _after_critique(state: StudioState) -> str:
    if not state.get("visual_ok", False) and state.get("iterations", 0) < state.get("max_iterations", 3):
        return "reviser"
    return "judge"


def _after_judge(state: StudioState) -> str:
    if not state.get("judge_pass", False) and state.get("iterations", 0) < state.get("max_iterations", 3):
        return "proposer"
    return END


def build_graph():
    g = StateGraph(StudioState)
    g.add_node("framer", nodes.framer)
    g.add_node("proposer", nodes.proposer)
    g.add_node("critic_panel", nodes.critic_panel)
    g.add_node("compile", nodes.compile_node)
    g.add_node("critique", nodes.multimodal_critique)
    g.add_node("reviser", nodes.reviser)
    g.add_node("judge", nodes.judge)

    g.add_edge(START, "framer")
    g.add_edge("framer", "proposer")
    g.add_edge("proposer", "critic_panel")
    g.add_edge("critic_panel", "compile")
    g.add_edge("compile", "critique")
    g.add_conditional_edges("critique", _after_critique, {"reviser": "reviser", "judge": "judge"})
    g.add_edge("reviser", "compile")
    g.add_conditional_edges("judge", _after_judge, {"proposer": "proposer", END: END})
    return g.compile()


def run_studio(brief: InsightBrief, out_dir: str, *, max_iterations: int = 3) -> dict:
    """Run the graph on one insight; returns the final state (png_path, chosen encoding, judge)."""
    graph = build_graph()
    return graph.invoke(
        {"brief": brief, "out_dir": out_dir, "max_iterations": max_iterations, "iterations": 0},
        config={"recursion_limit": 30},
    )
