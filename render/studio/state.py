"""The LangGraph state passed between Chart Studio nodes."""
from __future__ import annotations

from typing import TypedDict

from .encoding import ChartEncoding
from .insight import InsightBrief


class StudioState(TypedDict, total=False):
    # inputs
    brief: InsightBrief
    out_dir: str
    max_iterations: int

    # framer
    message: str                 # the single communicative job
    candidate_marks: list[str]   # the forms worth proposing

    # proposer / critic
    candidates: list[ChartEncoding]
    chosen: ChartEncoding
    critique_rationale: str

    # compile / multimodal critique loop
    png_path: str
    visual_ok: bool
    visual_feedback: str
    iterations: int

    # judge
    judge_pass: bool
    judge_notes: str
