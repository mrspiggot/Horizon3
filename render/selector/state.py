"""The LangGraph state passed between Model-Selection nodes."""
from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field


class Pick(BaseModel):
    """One model this decision-maker should run, and why."""
    model_id: str = Field(description="the EXACT model id from the offered library")
    why: str = Field(description="what this model tells THIS decision-maker about THIS decision — "
                                 "one sentence, specific to the decision, not a description of the model")


class Picks(BaseModel):
    picks: list[Pick] = Field(default_factory=list)


class SelectState(TypedDict, total=False):
    # inputs
    persona_id: str
    decision: str
    default_models: list[str]     # what personas.yaml hardcodes — the floor, never the ceiling
    library: list[dict]           # every PROVEN executable model in the spine
    min_models: int
    max_models: int
    max_iterations: int

    # propose
    picks: list[Pick]
    feedback: str                 # why the last proposal was unusable
    iterations: int

    # validate
    rejected: list[str]           # picks that named a model the graph cannot run — the LLM's fault
    selected: list[str]
    reasons: dict                 # model_id -> why
