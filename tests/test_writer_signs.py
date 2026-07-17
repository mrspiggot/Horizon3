"""Sign doubling in figure prose — the defect a fully-grounded article shipped with.

"leaving a stance of just ++0.18pp" reached a reader on 2026-07-17 in an article the Judge passed as
GROUNDED: True. It was right to: the arithmetic is correct, +0.18pp is exactly what the model
produced. A doubled sign is not a claim, so no claim-checker can see it. Only a human reading the
prose catches this — which is hard rule #1, and why the rule exists.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.writer import _finalize_text  # noqa: E402


class _No:
    """Minimal stand-in for a NumberObject: rendered() carries the sign and the unit."""
    def __init__(self, r, unit=""):
        self._r, self.unit = r, unit

    def rendered(self):
        return self._r


def test_writer_supplied_plus_is_absorbed():
    t, _ = _finalize_text("a stance of just +{n1}", {"n1": _No("+0.18pp", "pp")})
    assert t == "a stance of just +0.18pp", t


def test_writer_supplied_minus_is_absorbed():
    t, _ = _finalize_text("a gap of -{n1}", {"n1": _No("-1.38pp", "pp")})
    assert t == "a gap of -1.38pp", t


def test_bare_token_is_untouched():
    t, _ = _finalize_text("the stance reads {n1} today", {"n1": _No("+0.18pp", "pp")})
    assert t == "the stance reads +0.18pp today", t


def test_a_mismatched_sign_is_left_alone_not_silently_rewritten():
    # "-{n}" where n renders POSITIVE means the writer meant something else. Absorbing the minus would
    # turn a visible oddity into a clean-looking number that says the opposite of what was written.
    t, _ = _finalize_text("down -{n1}", {"n1": _No("+0.18pp", "pp")})
    assert t == "down -+0.18pp", t


def test_unsigned_values_are_unaffected():
    t, _ = _finalize_text("odds of {n1}", {"n1": _No("16%", "%")})
    assert t == "odds of 16%", t
