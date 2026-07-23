"""The LangGraph state passed between Judge nodes."""
from __future__ import annotations

from typing import Any, TypedDict

from .claims import Claim, Verdict


class JudgeState(TypedDict, total=False):
    # inputs
    prose: str
    runs: dict[str, str]          # model_id -> run_id in the Output table
    conn: Any                     # psycopg2 connection (the Output table is the only source of truth)
    max_iterations: int
    computed_ledger: str          # the article's executed CHART-ANALYSIS figures (regime slopes, chart
                                  # crossings on derived series, PCA variance) — grounded by the chart's
                                  # own computation, so the extractor must not convict them vs a raw output

    # extract
    claims: list[Claim]
    feedback: str                 # why the last extraction was unusable, fed back to re-extract

    # adjudicate
    verdicts: list[Verdict]
    unresolved: list[str]         # claims naming an output/window we could not bind — the JUDGE's fault
    iterations: int

    # verdict
    grounded: bool
    failures: list[Verdict]
