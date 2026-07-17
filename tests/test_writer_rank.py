"""Draft ranking: grounding outranks style.

The loop shipped the LAST draft until 3da5fcd; now it ships the best. But the first ranking was flat,
so "lints clean + critic ok" (4) beat "lints clean + grounded" (3) — and volatility_trader duly
shipped rank 4/4 "lints clean, critic ok" with grounded=False on 2026-07-17.

A graceful sentence the arithmetic cannot confirm is worth less than an awkward one it can. That is
the whole thesis of the Judge, and the ranking said the opposite.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _rank(leak_free: bool, is_grounded: bool, is_crit_ok: bool) -> int:
    # Mirrors render.writer.build_article_full._rank (a closure over the loop's state).
    if not leak_free:
        return 0
    return 1 + (2 if is_grounded else 0) + (1 if is_crit_ok else 0)


def test_a_leaking_draft_is_always_worst():
    # An untraced figure puts a number in front of a reader that no model produced.
    assert _rank(False, True, True) < _rank(True, False, False)


def test_grounded_beats_critic_clean():
    # The inversion that shipped: rank(clean+critic) must NOT beat rank(clean+grounded).
    assert _rank(True, True, False) > _rank(True, False, True)


def test_grounded_and_critic_clean_is_the_best():
    assert _rank(True, True, True) == 4
    assert _rank(True, True, True) > _rank(True, True, False)


def test_ordering_is_total_and_unsurprising():
    assert [_rank(False, False, False), _rank(True, False, False), _rank(True, False, True),
            _rank(True, True, False), _rank(True, True, True)] == [0, 1, 2, 3, 4]
