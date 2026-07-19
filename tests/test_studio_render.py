"""Studio compile-layer rendering guards (P3/P4/P5 — the v6 chart-execution cluster)."""
import numpy as np
import pandas as pd

from render.studio.compile import _ordinal_order, _robust_vlim, _sorted_for_x, _tenor_key


def test_robust_vlim_clips_a_spike_so_the_surface_does_not_wash_out():
    # a vol surface: ~130 months of 14-20 baseline, a 2-month COVID spike to ~75. The scale must anchor
    # near the baseline top (~20), not the spike (~75), or the whole surface collapses into one band.
    base = np.random.default_rng(0).uniform(14, 20, size=(4, 130))
    base[:, 40:42] = 75.0
    lo, hi = _robust_vlim(base, diverging=False)
    assert 18 < hi < 30            # anchored on the bulk, not the 75 spike
    assert lo < 16
    # diverging: symmetric about 0, anchored on the 95th pct of |value|, not the max
    d = np.concatenate([np.full(100, 0.4), np.full(3, 9.0)])
    vlo, vhi = _robust_vlim(d, diverging=True)
    assert vhi == -vlo and vhi < 9.0


def test_tenor_key_parses_days_weeks_months_years_and_rates_slang():
    assert _tenor_key("9d") == 9.0
    assert _tenor_key("1m") == 30.0
    assert _tenor_key("6m") == 180.0
    assert _tenor_key("1y") == 365.0
    assert _tenor_key("10Y") == 3650.0
    assert _tenor_key("2s") == 730.0            # rates slang: 2s = 2-year
    assert _tenor_key("hello") is None          # not a tenor → None (so authored order is preserved)
    assert _tenor_key("real yield") is None


def test_ordinal_order_is_monotonic_not_lexical():
    # the exact mis-sorts the review flagged: "10y" before "1y", "9d" after "6m"
    assert _ordinal_order(["10y", "1y", "5y", "2y"]) == ["1y", "2y", "5y", "10y"]
    assert _ordinal_order(["1m", "3m", "6m", "9d"]) == ["9d", "1m", "3m", "6m"]
    assert _ordinal_order(["risk", "credit", "leverage"]) is None   # non-tenor → preserve authored order


def test_glyph_safe_replaces_missing_arrows_and_collapses_spaces():
    from render.studio.compile import _glyph_safe
    assert "→" not in _glyph_safe("Tenor (short → long)")
    assert _glyph_safe("short → long") == "short to long"       # no double space
    assert _glyph_safe("2s → 5s → 10s") == "2s to 5s to 10s"
    assert _glyph_safe("plain text") == "plain text"            # untouched when no glyph


def test_subtitle_wraps_at_word_boundary_never_mid_word():
    from render.studio.compile import _sub
    long = "Implied vol by tenor: the front is cheap and the term structure slopes gently upward today"
    out = _sub(long, 40)
    assert "\n" in out                                          # wrapped to multiple lines
    for line in out.replace("…", "").split("\n"):
        assert not line.endswith("-") and " " in line or line   # no mid-word hyphen cut
    # over the 2-line budget → ends with an ellipsis at a word boundary, not a mid-word chop
    verylong = " ".join(["word%d" % i for i in range(60)])
    out2 = _sub(verylong, 30)
    assert out2.endswith("…") and out2.count("\n") == 1


def test_series_labels_are_reader_labels_not_raw_columns():
    from render.studio.from_model import _authored_labels, _label
    # humanised, not the raw DB column (the v6 garbled-legend class)
    assert _label("gz_spread", "level") == "GZ spread"
    assert _label("ebp", "level") == "Excess bond premium"
    assert "pct" not in _label("risk_free_pct", "level").lower()
    assert "pp" not in _label("sahm_gap_pp", "level").split()
    # an authored catalog label wins over the humanised field name
    dc = {"layers": [{"label": "IG credit spread", "from": "output:credit_oas_pct"}]}
    assert _authored_labels(dc)["credit_oas_pct"] == "IG credit spread"


def test_sorted_for_x_orders_tenor_axis_monotonically_but_leaves_nominal_alone():
    g = pd.DataFrame({"item": ["10y", "1y", "6m", "9d"], "v": [4, 3, 2, 1]})
    out = list(_sorted_for_x(g, "item", "nominal")["item"])
    assert out == ["9d", "6m", "1y", "10y"]     # upward contango order, 9d at the left
    # a genuine nominal axis keeps its authored order (no lexical reshuffle)
    g2 = pd.DataFrame({"item": ["risk", "credit", "leverage"], "v": [1, 2, 3]})
    assert list(_sorted_for_x(g2, "item", "nominal")["item"]) == ["risk", "credit", "leverage"]
