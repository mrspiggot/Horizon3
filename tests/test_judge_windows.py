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
    # The point is that it RESOLVES AT ALL. (The date is the episode's end: "since X" means after
    # X — see test_since_the_gfc_prefers_after_the_gfc.)
    assert _resolve_since("the taper tantrum") is not None
    assert _resolve_since("the GFC") is not None


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
    # The quote must STATE the figure — a percentile claim whose prose names no number is refused
    # outright now, because the extractor was inventing them. See the number-authoring tests below.
    return Claim(quote=f"unemployment sits at the {pct}th percentile of its history", kind="percentile",
                 model_id="m", output="unemployment_pct", pct=pct, scope=scope)


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


# --- settled vs ok: the distinction that cost three true sentences ---------------------------------
def test_unresolvable_window_is_the_judges_failure_not_the_proses():
    # SHIPPED FEEDBACK: "a swing in 2024 to the most restrictive reading against r* in years"
    # -> "unresolvable window 'years' — a superlative needs a start" -> counted as a CONTRADICTION.
    # The judge could not read "in years". That is not evidence the writer lied.
    v = adjudicate(Claim(quote="the most restrictive reading against r* in years", kind="superlative",
                         model_id="m", output="stance_pct", op="max", since="years"), _SPREAD)
    assert not v.settled
    assert not any(x.settled and not x.ok for x in [v]), "an unresolvable window must never convict"


def test_multi_period_sentence_describes_shape_and_is_not_adjudicated():
    # SHIPPED FEEDBACK: "nowhere near the peaks above 20 the index printed in 1975 and 1980" was
    # convicted because the max is 1980, not 1975. The sentence never claimed 1975 held the record —
    # it says today is small, which is true, and names both peaks.
    v = adjudicate(Claim(quote="nowhere near the peaks above 20 the index printed in 1975 and 1980",
                         kind="episode", model_id="m", output="misery_index", op="max", at="1975"),
                   _SPREAD)
    assert not v.settled, "a sentence naming several periods must not be crowned or convicted"


def test_a_real_contradiction_is_still_settled_and_convicted():
    # The guard rail must not swallow the genuine catch. This is the sentence that shipped to a reader.
    stance = [(date(2024, 8, 28), 2.27), (date(2026, 5, 28), 0.18)]
    v = adjudicate(Claim(quote="the most restrictive setting since the financial crisis",
                         kind="superlative", model_id="m", output="stance_pct", op="max",
                         since="the financial crisis"), stance)
    assert v.settled and not v.ok, "the real contradiction must still convict"


# --- the judge must not author numbers (hard rule #2, broken BY the judge) --------------------------
def test_qualitative_phrase_is_not_a_percentile_claim():
    # SHIPPED FEEDBACK: the prose said "the stance now sits near the bottom of its range" — no figure
    # anywhere. The extractor invented pct=10 and the arithmetic convicted the writer against the
    # LLM's own invention. The claim and the evidence were both fabricated; the sentence was true.
    v = adjudicate(Claim(quote="the stance now sits near the bottom of its range", kind="percentile",
                         model_id="m", output="stance_pct", pct=10, scope="recent"), _UNEMP)
    assert not v.settled
    assert "never authors a number" in v.detail


def test_a_stated_percentile_is_still_adjudicated():
    assert adjudicate(_pct_claim(78), _UNEMP).settled          # "the 78th percentile" — a real figure
    v = adjudicate(Claim(quote="an eighth-percentile reading", kind="percentile", model_id="m",
                         output="unemployment_pct", pct=8, scope="full"), _UNEMP)
    assert v.settled, "written-out ordinals state a number too"


def test_episode_tolerates_prose_rounding_across_a_year_boundary():
    # The Taylor prescription peaks 1981-01-28. "the peak of 1980" is how everyone writes about
    # Volcker, and convicting it for one month is pedantry that gets a check switched off.
    volcker = [(date(1981, 1, 28), 14.02), (date(2026, 5, 28), 5.31)]
    assert adjudicate(Claim(quote="the peak it hit in 1980", kind="episode", model_id="m",
                            output="taylor_1993", op="max", at="1980"), volcker).ok


def test_grace_does_not_rescue_a_real_misattribution():
    spike = [(date(2020, 4, 28), 14.8), (date(2026, 1, 28), 4.3)]
    v = adjudicate(Claim(quote="the 2022 spike", kind="episode", model_id="m",
                         output="unemployment_pct", op="max", at="2022"), spike)
    assert v.settled and not v.ok, "two years off is a misattribution, not rounding"


# --- decades: prose talks in them; the parser had no concept of one --------------------------------
def test_early_1980s_is_a_decade_not_the_year_1980():
    # SHIPPED FEEDBACK: "nowhere near the near-14% peak the rule reached in the disinflation of the
    # early 1980s" was convicted because the parser read "early"+"1980" as months 1-7 of 1980. The
    # prescription peaks 1981-01-28 — squarely in the early 1980s. The sentence is true.
    lo, hi = _resolve_window("the early 1980s")
    assert lo <= "1981-01-28" <= hi


def test_decade_variants():
    assert _resolve_window("the 2010s") == ("2010-01-01", "2019-12-31")
    assert _resolve_window("the late 1990s") == ("1996-01-01", "1999-12-31")
    lo, hi = _resolve_window("the mid-1970s")
    assert lo <= "1975-06-01" <= hi


def test_a_bare_year_still_means_that_year_not_its_decade():
    assert _resolve_window("1980") == ("1980-01-01", "1980-12-31")


# --- "since X" means AFTER X, and it is ambiguous ---------------------------------------------------
def test_since_the_gfc_prefers_after_the_gfc():
    # AUDIT FALSE POSITIVE: real_funding's "the post-2022 climb back to the heaviest since the GFC" is
    # TRUE — the post-2022 peak of 4.22 (2023-10) IS the highest since 2010. It was convicted because
    # "since the GFC" resolved to the GFC's START (2007), and 2008 printed 7.70.
    assert _resolve_since("the GFC") == "2010-01-01"


def test_superlative_is_spared_when_one_reading_supports_it():
    # Today IS the highest since the GFC ended; 2008 was higher, but "since the GFC" idiomatically
    # excludes the crisis itself. One reading supports the claim, so it must not be convicted.
    real_funding = [(date(2008, 11, 28), 7.70), (date(2023, 10, 28), 3.90), (date(2026, 7, 28), 4.22)]
    v = adjudicate(Claim(quote="the heaviest since the GFC", kind="superlative", model_id="m",
                         output="real_funding", op="max", since="the GFC"), real_funding)
    assert v.ok, v.detail          # true after the GFC; only the from-2007 reading fails it


def test_the_cb_catch_survives_both_readings():
    # The sentence that shipped. It must still convict under EVERY reading of "the financial crisis" —
    # the loosening above must not blunt the one catch that matters.
    stance = [(date(2008, 6, 28), 1.10), (date(2024, 8, 28), 2.27), (date(2026, 5, 28), 0.18)]
    v = adjudicate(Claim(quote="the most restrictive setting since the financial crisis",
                         kind="superlative", model_id="m", output="stance_pct", op="max",
                         since="the financial crisis"), stance)
    assert v.settled and not v.ok, "the 2024 peak beats today under both readings — still false"


def test_superlative_ties_do_not_convict():
    # max() returns the EARLIER date on a tie, so a series back at exactly its prior high was
    # convicted for a true claim. Compare values, not dates.
    tied = [(date(2015, 1, 28), 5.0), (date(2026, 1, 28), 5.0)]
    v = adjudicate(Claim(quote="the highest since 2010", kind="superlative", model_id="m",
                         output="x", op="max", since="2010"), tied)
    assert v.ok, v.detail


def test_a_benign_skip_does_not_block_grounded():
    # A sentence describing a curve's shape, or stating no figure, is not an open question. Routing
    # these to `unresolved` (which blocks `grounded`) meant an article could carry sound prose and
    # never be certifiable — and the writer would burn its whole iteration budget re-extracting.
    shape = adjudicate(Claim(quote="the peaks in 1975 and 1980", kind="episode", model_id="m",
                             output="x", op="max", at="1975"), _SPREAD)
    qual = adjudicate(Claim(quote="near the bottom of its range", kind="percentile", model_id="m",
                            output="x", pct=10), _SPREAD)
    assert not shape.retry and not qual.retry, "benign skips must not demand re-extraction"


def test_an_unresolvable_window_does_demand_a_retry():
    # This one the extractor really could do better on, and the judge genuinely has not checked the
    # sentence — so it must block `grounded` rather than pass silently.
    v = adjudicate(Claim(quote="the most restrictive in years", kind="superlative", model_id="m",
                         output="x", op="max", since="years"), _SPREAD)
    assert not v.settled and v.retry


_RF = [(date(2008, 11, 28), 7.70), (date(2023, 10, 28), 4.22), (date(2026, 7, 28), 3.64)]


def test_superlative_naming_a_year_is_read_as_an_episode():
    # "the 2023 peak, the heaviest since the GFC" — TRUE: the 2023 peak of 4.22 IS the heaviest since
    # 2010. Typed superlative by the extractor and convicted because today is 3.64. The prompt's tense
    # rule was ignored all day; this enforces it.
    v = adjudicate(Claim(quote="a 2023 peak, the heaviest since the GFC", kind="superlative",
                         model_id="m", output="real_funding", op="max", since="the GFC"), _RF)
    assert v.ok, v.detail


def test_superlative_tracing_several_years_is_not_adjudicated():
    # "the post-2022 climb to a 2023 peak, the heaviest since the GFC" traces a curve across two
    # named years. Neither convicting nor confirming it means anything.
    v = adjudicate(Claim(quote="the post-2022 climb to a 2023 peak, the heaviest since the GFC",
                         kind="superlative", model_id="m", output="real_funding", op="max",
                         since="the GFC"), _RF)
    assert not v.settled and not v.retry


def test_the_shipped_sentence_names_no_year_and_still_convicts():
    # The sentence that reached a reader names no year — it is a claim about NOW, and stays one.
    stance = [(date(2024, 8, 28), 2.27), (date(2026, 5, 28), 0.18)]
    v = adjudicate(Claim(quote="the most restrictive setting relative to the natural rate since the "
                               "financial crisis", kind="superlative", model_id="m",
                         output="stance_pct", op="max", since="the financial crisis"), stance)
    assert v.settled and not v.ok


def test_a_year_that_is_the_since_anchor_does_not_convert():
    # "the highest since 2010" names 2010 as its WINDOW, not as where the peak sits.
    pts = [(date(2015, 1, 28), 9.0), (date(2026, 1, 28), 4.0)]
    v = adjudicate(Claim(quote="the highest since 2010", kind="superlative", model_id="m",
                         output="x", op="max", since="2010"), pts)
    assert v.kind == "superlative" and not v.ok


def test_a_decade_in_the_quote_stays_a_decade():
    # "accommodative through the 2010s, then the swing to the most restrictive since the GFC": the
    # converter must hand "2010s" downstream, not "2010" — a ten-year span, not one year.
    stance = [(date(2011, 4, 28), -3.36), (date(2024, 8, 28), 2.27), (date(2026, 5, 28), 0.18)]
    v = adjudicate(Claim(quote="accommodative through the 2010s", kind="superlative", model_id="m",
                         output="stance_pct", op="min", since="the GFC"), stance)
    assert "2010-01..2019-12" in v.detail, v.detail
