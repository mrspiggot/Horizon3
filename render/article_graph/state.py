"""The LangGraph state threaded between article-graph nodes.

One object every node reads and writes — the shared interpretation-state the whole design turns on:
the executed material, the winning draft, the section↔chart bindings, and the finished artifacts are
all fields here, so charts, prose, and the dashboard are projections of ONE state rather than three
artifacts built from three unsynchronised sources.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ArticleState(TypedDict, total=False):
    # inputs
    persona_id: str
    conn: Any
    out_dir: str
    backend: str
    max_iter: int

    # material + plan
    mat: dict                    # executed models, numbers, concept registry (D)
    brief: dict                  # token menu, fact sheets, chart index, data-window firewall
    outline: Any                 # the section editor's Outline

    # the winning draft (best-of-N)
    draft: dict                  # full_text, standfirst, exec_summary, filled_sections, grounded, …

    # reconciliation outputs
    bindings: list               # SectionBinding per section (A)
    cited_keys: list             # concept keys the prose actually cited (C)
    ill_png: Any
    ill_meta: dict
    infog_png: Any

    # output
    result: dict
