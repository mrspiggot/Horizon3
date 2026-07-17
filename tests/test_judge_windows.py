"""Window/episode resolution. Every case here FAILED on the first version of claims.py, and every
failure was the same shape: the judge convicting TRUE prose because it could not parse the period.

That is the one bug class this file must not have. A judge that fails honest work gets switched off,
and a check nobody trusts protects nothing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.judge.claims import _resolve_since, _resolve_window  # noqa: E402


def test_year_month_is_a_month_not_a_year_range():
    # '2023-06' satisfied the old year-range test and resolved to ('2023-01-01', '06-12-31').
    # "the trough it reached in mid-2023" was failed as unshowable against that garbage window.
    assert _resolve_window("2023-06") == ("2023-06-01", "2023-06-30")


def test_year_range_still_works():
    assert _resolve_window("2021-2022") == ("2021-01-01", "2022-12-31")


def test_vague_half_of_a_year_resolves_generously():
    lo, hi = _resolve_window("mid-2023")
    assert lo <= "2023-06-15" <= hi          # whatever 'mid' means, it means June


def test_bare_year_and_episode():
    assert _resolve_window("2022") == ("2022-01-01", "2022-12-31")
    assert _resolve_window("COVID") == ("2020-01-01", "2020-12-31")


def test_month_end_is_the_real_last_day():
    # _pad hardcoded '-28', silently dropping 29-31 from every month-scoped claim.
    assert _resolve_window("2021-01/2022-12") == ("2021-01-01", "2022-12-31")
    assert _resolve_window("2024-02")[1] == "2024-02-29"      # leap year


def test_lstrip_the_does_not_eat_the_word():
    # `"the taper tantrum".lstrip("the ")` -> "aper tantrum": lstrip takes a CHARACTER SET, not a
    # prefix. The episode never matched, so "since the taper tantrum" was ruled unresolvable and the
    # claim FAILED — a false accusation against a sentence that may well be true.
    assert _resolve_since("the taper tantrum") == "2013-05-01"
    assert _resolve_since("the GFC") == "2007-01-01"


def test_since_accepts_dates_and_bare_years():
    assert _resolve_since("2019-03") == "2019-03-01"
    assert _resolve_since("2019-03-14") == "2019-03-14"
    assert _resolve_since("since 2015") == "2015-01-01"


def test_unparseable_period_returns_none_rather_than_a_guess():
    assert _resolve_window("whenever") == (None, "")
    assert _resolve_since("a while back") is None


# --- episode: WHERE IN TIME the extreme sits -------------------------------------------------------
from datetime import date  # noqa: E402

from render.judge.claims import Claim, adjudicate  # noqa: E402

_SPREAD = [(date(2023, 6, 28), -1.73), (date(2024, 6, 28), -0.40), (date(2026, 7, 28), 0.73)]


def test_episode_confirms_a_correctly_placed_trough():
    # "the trough it reached in mid-2023, the most inverted point" — TRUE: min IS 2023-06.
    # With no episode type the extractor forced this into a superlative and it was convicted.
    v = adjudicate(Claim(quote="the trough it reached in mid-2023", kind="episode", model_id="m",
                         output="term_spread_pp", op="min", at="mid-2023"), _SPREAD)
    assert v.ok, v.detail


def test_episode_catches_a_misattributed_spike():
    # The defect an editor caught by eye: "the 2022 spike" when the spike is 2020.
    v = adjudicate(Claim(quote="the 2024 trough", kind="episode", model_id="m",
                         output="term_spread_pp", op="min", at="2024"), _SPREAD)
    assert not v.ok
    assert "NOT in that period" in v.detail


# --- percentile: the type whose absence let two false sentences ship --------------------------------
_UNEMP = [(date(1950 + i // 12, i % 12 + 1, 28), v) for i, v in
          enumerate([9.0] * 30 + [3.0] * 40 + [14.8] + [4.3] * 29)]


def _pct_claim(pct, scope="full"):
    return Claim(quote="q", kind="percentile", model_id="m", output="unemployment_pct",
                 pct=pct, scope=scope)


def test_percentile_catches_the_backwards_claim():
    # SHIPPED: "Unemployment stands at 4.30%, high in its own post-1948 history at the 78th
    # percentile". It is the 23rd percentile since 1948 — historically LOW. The article said the
    # opposite of the truth, because the fact sheet labelled a trailing-60 window "its own history".
    v = adjudicate(_pct_claim(78), _UNEMP)
    assert not v.ok, v.detail
    assert "off by" in v.detail


def test_percentile_accepts_the_true_reading():
    actual = round(sum(1 for _, x in _UNEMP if x < 4.3) / len(_UNEMP) * 100)
    assert adjudicate(_pct_claim(actual), _UNEMP).ok


def test_percentile_tolerates_a_writer_rounding():
    actual = round(sum(1 for _, x in _UNEMP if x < 4.3) / len(_UNEMP) * 100)
    assert adjudicate(_pct_claim(actual + 6), _UNEMP).ok      # rounding, not a lie


def test_percentile_scope_recent_is_a_different_question():
    # Both numbers are legitimate; they answer different questions. The bug was reporting one under
    # the other's name.
    full = adjudicate(_pct_claim(23, "full"), _UNEMP)
    recent = adjudicate(_pct_claim(23, "recent"), _UNEMP)
    assert full.detail != recent.detail
