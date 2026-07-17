"""Judge nodes: extract (LLM) → adjudicate (arithmetic) → verdict."""
from __future__ import annotations

import sys

from ..model_store import output_series
from ..studio.llm import get_llm
from .claims import EPISODES, Claims, Verdict, adjudicate
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

Extract only these five kinds:

  percentile  — the text places the CURRENT value at a percentile of its history.
                e.g. "Unemployment stands at 4.30%, high in its own post-1948 history at the 78th
                percentile" -> kind=percentile, output=unemployment_pct, pct=78, scope=full
                e.g. "back in the 22nd percentile of their own history" -> pct=22, scope=full
                e.g. "an eighth-percentile reading" -> pct=8
                ONLY when the text STATES the figure. "near the bottom of its range", "near the top",
                "low by post-war standards", "elevated" state NO percentile — DO NOT convert them into
                one. Supplying the number yourself is authoring a number, which you must never do: the
                writer is then convicted against a figure you invented, and the sentence was true.
                `scope`: use "full" when the text ties it to the whole record ("since 1948",
                "post-war", "of its own history", "ever printed"); "recent" only when the text
                explicitly says the last few years. A percentile sentence is NOT a superlative —
                "near the low end" is not "the lowest". Do not emit it as one.

  superlative — the text asserts THE CURRENT VALUE is the highest/lowest/most/least since some point.
                THE TEST IS THE TENSE. "the stance NOW READS the most restrictive since the financial
                crisis" -> kind=superlative, op=max, output=stance_pct, since="the financial crisis".
                But "THE 2024 SWING to the most restrictive setting since the GFC" is about 2024, so it
                is an `episode` (op=max, at="2024") — and it is TRUE, because the high really is
                2024-08. Read as a superlative it is convicted, because today is +0.18pp. Same words,
                opposite verdict: if the sentence names WHEN, it is an episode. Do not default to
                superlative because the words "most ... since" appear.
  episode     — the text places a peak/trough AT A TIME. The claim is WHEN the extreme happened, not
                that today is extreme.
                e.g. "a decisive reversal from the trough it reached in mid-2023, the most inverted
                point the probit has read" -> kind=episode, op=min, output=term_spread_pp, at="mid-2023"
                ONLY emit this when the text asserts THE ONE extreme of the whole series — "the most
                inverted point it has read", "its record high", "the deepest trough". The adjudicator
                answers exactly one question: is the series' global high/low inside that period?
                DO NOT emit it for a local bump, or when the sentence names SEVERAL highs. "its 1975
                and 1980 peaks near twenty, the benign 2015-19 trough, and the 2022 spike" describes
                the SHAPE of a curve; it does not claim 1975 or 2022 holds the record, and treating it
                as if it did convicts an accurate sentence. If the prose lists more than one peak, or
                calls it "a" spike rather than "the" peak, SKIP IT.
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
                claim is the RECENT one: kind=direction, output=r_star_pct, expect=up
                SET `window_months` ONLY IF THE TEXT NAMES A PERIOD ("over the past year" -> 12).
                Vague words — "recently", "lately", "of late" — are NOT a period: leave window_months
                unset and several readings will be tried. Inventing a window is how a judge convicts a
                true sentence: r* is +0.15 over 12m and -0.03 over 36m, so a guessed 36 turns a
                defensible claim into a contradiction.

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
- A DEFINITION IS NOT A CLAIM. Text that explains what a chart ENCODES or what a threshold MEANS
  asserts nothing about today: "the yield-curve slope the model reads; inversion (below 0) is the
  signal" is a legend — it says what below-zero would mean, not that the series is below zero now.
  Same for "restrictive above zero", "positive readings indicate tightening", "(>0 = expansion)".
  Emitting these as regime claims convicts a caption for correctly labelling its own axis.
- Be exhaustive on the five kinds and silent on everything else.

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
        v = adjudicate(c, series)
        verdicts.append(v)
        # The judge failing to settle a claim is the JUDGE's problem. Route it back for a cleaner
        # extraction; never hand it to the writer as evidence its sentence is wrong.
        # Only `retry` cases go back: a sentence that is CORRECTLY not adjudicable (it describes a
        # curve's shape, or states no figure) is not an open question, and treating it as one made
        # every article carrying one ungrounded no matter how sound its prose.
        if not v.settled and v.retry:
            unresolved.append(f"{c.output}: {v.detail}")
    return {"verdicts": verdicts, "unresolved": unresolved,
            "feedback": "; ".join(unresolved[:4]) if unresolved else ""}


def verdict(state: JudgeState) -> dict:
    vs = state.get("verdicts") or []
    # ONLY a settled claim can convict. An unsettled one means the judge could not resolve the window,
    # bind the output, or read the sentence — all of which are its own failure. Counting those as
    # contradictions told the writer to rewrite three TRUE sentences on 2026-07-17.
    failures = [v for v in vs if v.settled and not v.ok]
    for v in failures:
        print(f"UNGROUNDED — {v.output}: {v.quote[:70]!r}\n    {v.detail}", file=sys.stderr)
    # Unresolved claims mean the Judge could not do its job — that is not a pass. Silence here is the
    # failure mode this whole role exists to end.
    grounded = not failures and not state.get("unresolved")
    return {"grounded": grounded, "failures": failures}
