"""Judge nodes: extract (LLM) → adjudicate (arithmetic) → verdict."""
from __future__ import annotations

import sys

from ..model_store import output_series
from ..studio.llm import get_llm
from .claims import EPISODES, Claim, Claims, Verdict, adjudicate
from .state import JudgeState

REASONING_MODEL = "claude-opus-4-8"


def _offered_outputs(runs: dict, conn) -> str:
    """The EXACT outputs this article was written from — the closed vocabulary the extractor may bind
    to. Constrained, per the repo's own rule (mapper.py: "can only choose labels that already exist —
    it never invents"). An extractor free to invent an output name produces claims nothing can settle.
    """
    lines = []
    with conn.cursor() as cur:
        for mid, rid in runs.items():
            cur.execute("SELECT DISTINCT p.name, p.unit FROM model_output_point p WHERE p.run_id=%s "
                        "ORDER BY 1", (rid,))
            for name, unit in cur.fetchall():
                cur.execute("SELECT min(as_of), max(as_of), count(*) FROM model_output_point "
                            "WHERE run_id=%s AND name=%s", (rid, name))
                lo, hi, n = cur.fetchone()
                # model_id and output are SEPARATE fields. Showing them joined ("policy_stance.
                # stance_pct") made the extractor put the dotted string into model_id and every claim
                # failed to bind. State the two fields explicitly rather than hope.
                lines.append(f'  model_id="{mid}"  output="{name}"  ({unit or "-"}) '
                             f'— executed {lo} → {hi}, {n} points')
    return "\n".join(lines)


_EXTRACT = """You are the claim EXTRACTOR for a financial article's fact-check. You do NOT judge truth.
Your only job is to find every sentence that makes a CHECKABLE ASSERTION ABOUT AN EXECUTED MODEL
OUTPUT, and express it as a typed claim. Arithmetic will settle it afterwards.

Extract only these three kinds:

  superlative — the text asserts the CURRENT value is the highest/lowest/most/least since some point.
                e.g. "the most restrictive setting relative to the natural rate since the financial
                crisis" -> kind=superlative, op=max, output=stance_pct, since="the financial crisis"
                NOT a superlative: "its peaks near twenty percent in 1975 and 1980" — that DESCRIBES
                past peaks, it does not claim today is the extreme. Do not emit it. A superlative is
                only a superlative when the claim is about NOW being the most/least since a date.
  regime      — the text asserts where the series sits relative to zero, NOW or in a stated PAST
                period. THIS DISTINCTION IS CRITICAL — get it wrong and a true sentence is called a
                contradiction.
                present: "the signal is an inversion — the slope below zero" -> kind=regime,
                         output=term_spread_pp, predicate=below_zero  (no `during`)
                past:    "through 2021 and 2022 the ex-post rate went deeply negative" -> kind=regime,
                         output=real_rate_expost_pct, predicate=below_zero, during="2021-2022"
                If the sentence names a period, ALWAYS set `during`. Only omit it when the claim is
                genuinely about today.
  direction   — the text asserts which way the series has moved lately.
                e.g. "r* has drifted down through the 2010s, and more recently up" -> the operative
                claim is the RECENT one: kind=direction, output=r_star_pct, expect=up, window_months=36

RULES
- `output` MUST be one of the offered outputs below, exactly. Never invent a name. If a sentence makes
  a claim you cannot bind to an offered output, DO NOT emit it.
- EMIT ONLY WHAT FITS CLEANLY. A claim you have to bend to fit one of the three kinds is a claim you
  must skip. Precision beats recall here by a wide margin: a false accusation against true prose
  destroys trust in this check, and a check nobody trusts gets switched off and protects nothing.
  In particular, a claim comparing ONE SERIES TO ANOTHER ("the actual rate sits below the whole
  family", "implied exceeds realized") is NOT a regime claim — regime is only about a single series'
  sign versus zero. Skip it.
- `quote` must be the fragment from the prose, verbatim.
- Named episodes are fine in `since` ("the GFC", "the financial crisis", "COVID"): they are resolved
  downstream. Known: {episodes}.
- Ignore claims about things that are not model outputs (the Fed's intentions, what a chart shows,
  general economics). Ignore pure statements of a current value — those are checked elsewhere.
- Be exhaustive on the three kinds and silent on everything else.

OFFERED OUTPUTS (the only ones that exist):
{outputs}

{feedback}
ARTICLE PROSE:
{prose}
"""


def extract(state: JudgeState) -> dict:
    outputs = _offered_outputs(state["runs"], state["conn"])
    fb = state.get("feedback") or ""
    prompt = _EXTRACT.format(
        outputs=outputs, prose=state["prose"][:14000], episodes=", ".join(sorted(EPISODES)),
        feedback=(f"YOUR LAST ATTEMPT FAILED: {fb}\nFix it.\n\n" if fb else ""))
    llm = get_llm(model=REASONING_MODEL, temperature=0).with_structured_output(Claims)
    got: Claims = llm.invoke(prompt)
    return {"claims": got.claims, "iterations": state.get("iterations", 0) + 1}


def adjudicate_node(state: JudgeState) -> dict:
    """Arithmetic. Every claim is settled against the executed series — never against a model's memory."""
    conn, runs = state["conn"], state["runs"]
    verdicts: list[Verdict] = []
    unresolved: list[str] = []
    for c in state.get("claims") or []:
        # Be lenient about a dotted "model.output" arriving in either field — the binding is
        # unambiguous, and failing a true claim on a formatting nit would teach us nothing.
        mid, out = c.model_id, c.output
        if "." in mid:
            head, _, tail = mid.partition(".")
            if head in runs:
                mid, out = head, (tail or out)
        if "." in out:
            head, _, tail = out.partition(".")
            if head in runs:
                mid, out = head, tail
        c = c.model_copy(update={"model_id": mid, "output": out})
        rid = runs.get(c.model_id)
        if not rid:
            unresolved.append(f"{c.output}: model {c.model_id!r} was not run for this article")
            continue
        series = output_series(conn, rid, c.output)
        if not series:
            unresolved.append(f"{c.output!r} is not an output of {c.model_id} — bind to an offered name")
            continue
        verdicts.append(adjudicate(c, series))
    return {"verdicts": verdicts, "unresolved": unresolved,
            "feedback": "; ".join(unresolved[:4]) if unresolved else ""}


def verdict(state: JudgeState) -> dict:
    vs = state.get("verdicts") or []
    failures = [v for v in vs if not v.ok]
    for v in failures:
        print(f"UNGROUNDED — {v.output}: {v.quote[:70]!r}\n    {v.detail}", file=sys.stderr)
    # Unresolved claims mean the Judge could not do its job — that is not a pass. Silence here is the
    # failure mode this whole role exists to end.
    grounded = not failures and not state.get("unresolved")
    return {"grounded": grounded, "failures": failures}
