"""The Judge agent graph — §06 role 7: score model-grounding against the Output table.

    extract → adjudicate → verdict → END
       ▲                       │
       └───(unresolved)────────┘   (bounded by max_iterations)

§06, verbatim, on this role: "Judge — scores model-grounding and numerical discipline; failure routes
to revision. (This REPLACES the current gate battery's role, but with the right definition of 'done':
grounded and correct, not merely 'passed'.)"

What exists today instead: `writer.critique_article` gets `full_text[:9000]` and NO DATA. It is an
LLM scoring prose style against a StoryScope checklist. It cannot tell whether a sentence is TRUE,
because it has never seen a number. That is why "the most restrictive setting since the financial
crisis" shipped beside a series that peaked two years earlier at 12x the value — and why the article
was recorded `critic_ok=True`.

The shape is copied from render/studio/graph.py, which already proves the pattern in this repo:
a bounded StateGraph, LangSmith-traced, LLM proposing and a deterministic step disposing.

    the LLM EXTRACTS  — language: "since the GFC" -> 2007; "the slope below zero" -> a regime claim
                        about term_spread_pp. No regex reaches this; the existing firewall matches
                        4-digit years and "the GFC" has no digits.
    ARITHMETIC SETTLES — truth: claims.adjudicate() against model_output_point. The LLM never judges.
                        An LLM judge would have certified CPI 2.83% — it reads as a plausible print.
                        It was a 13-month change.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import JudgeState


def _after_adjudicate(state: JudgeState) -> str:
    # An unresolved claim (an output the extractor mis-named, an episode we have no window for) is a
    # FAILURE OF THE JUDGE, not of the prose. Re-extract with the reason; never silently pass it.
    if state.get("unresolved") and state.get("iterations", 0) < state.get("max_iterations", 2):
        return "extract"
    return "verdict"


def build_graph():
    g = StateGraph(JudgeState)
    g.add_node("extract", nodes.extract)
    g.add_node("adjudicate", nodes.adjudicate_node)
    g.add_node("verdict", nodes.verdict)
    g.add_edge(START, "extract")
    g.add_edge("extract", "adjudicate")
    g.add_conditional_edges("adjudicate", _after_adjudicate, {"extract": "extract", "verdict": "verdict"})
    g.add_edge("verdict", END)
    return g.compile()


def judge_article(prose: str, runs: dict, conn, *, max_iterations: int = 2) -> dict:
    """Judge one article's prose against the executed runs behind it.

    `runs` = {model_id: run_id} — the Output-table rows this article was written from.
    Returns the final state: {claims, verdicts, grounded, failures}.
    """
    return build_graph().invoke(
        {"prose": prose, "runs": runs, "conn": conn, "iterations": 0,
         "max_iterations": max_iterations, "feedback": ""},
        config={"recursion_limit": 12},
    )
