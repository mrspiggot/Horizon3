"""The digits/words contract: digits mean MEASURED, words mean APPROXIMATE.

The leak gate matches digits, and it fired on every draft of the CB article on 2026-07-17 — so the
Judge never ran and a rank-0 draft shipped. The three "leaks" were all TRUE statements the gate had
no legitimate way to express: "more than 100bp tighter" (the gap is ~140bp), "the 2% target" (a model
parameter), "around 1%" (r* is 1.06).

Forbidding rounding outright does not stop a writer needing to round; it just makes the gate fire
forever. The contract instead gives the figurative register a home — in WORDS — and keeps the digit
rule absolutely strict. Which also means closing the obvious hole: spelling a precise value out.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.writer import _worded_precision  # noqa: E402


def test_a_precise_value_spelled_out_is_caught():
    # The firewall matches digits, so "two point three nine percent" walks straight through it. Since
    # the fact sheet landed, the narrator can SEE 2.39 — it has something precise to disguise.
    assert _worded_precision("headline CPI at two point three nine percent") == "two point three nine"
    assert _worded_precision("an r* of one point zero six") == "one point zero six"


def test_hyphenated_and_mixed_case_are_caught():
    assert _worded_precision("Two-point-five percent") is not None


def test_legitimate_approximations_are_allowed():
    # This is the whole point: these must pass, or the writer has no way to be figurative and the
    # gate goes back to firing on every draft.
    for ok in ["more than a hundred basis points below its own rule",
               "an r* of around one percent",
               "the two percent target the rule anchors to",
               "peaks near twenty in the mid-1970s",
               "policy a full point below the prescription"]:
        assert _worded_precision(ok) is None, ok


def test_ordinary_prose_is_not_flagged():
    assert _worded_precision("the point is that neutral has moved") is None
    assert _worded_precision("at this point in the cycle") is None
