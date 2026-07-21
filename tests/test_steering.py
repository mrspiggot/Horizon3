"""The steering enumerator — the graph decides what to write (pure logic, no DB)."""
from render.steering import data_gaps, enumerate_analyses, port_backlog


def _facts():
    # a US-welded rates trader (all models US-only) and a generic economist (models run in US+EU)
    uses = {"rates": ["taylor", "term_premium", "recession"],          # all US-welded
            "economist": ["sahm", "phillips", "okun"]}                  # sahm/phillips generic, okun welded
    execin = {("taylor", "US"), ("term_premium", "US"), ("recession", "US"),
              ("sahm", "US"), ("sahm", "EU"), ("phillips", "US"), ("phillips", "EU"), ("okun", "US")}
    generic = {"taylor": False, "term_premium": False, "recession": False,
               "sahm": True, "phillips": True, "okun": False}
    blocked = {("sahm", "JP"): ["unemployment_rate"], ("phillips", "JP"): ["headline_cpi"]}
    return uses, execin, generic, blocked


def test_enumerator_grounds_by_currency_and_flags_near_misses():
    uses, execin, generic, blocked = _facts()
    got = enumerate_analyses(uses, execin, ["US", "EU", "JP"], {"rates": "set rates", "economist": "call it"},
                             min_models=3)
    g = {(a.decision_maker, a.jurisdiction): a for a in got}
    assert g[("rates", "US")].groundable and g[("rates", "US")].n == 3          # full US article
    assert not g[("rates", "EU")].groundable and g[("rates", "EU")].n == 0      # US-welded → nothing in EU
    assert g[("economist", "US")].groundable and g[("economist", "US")].n == 3
    assert not g[("economist", "EU")].groundable and g[("economist", "EU")].n == 2  # near-miss (2 of 3 in EU)
    assert "okun" in g[("economist", "EU")].missing_models                      # names what's missing
    # groundable analyses sort ahead of near-misses
    assert [a for a in got if a.groundable][0].groundable is True


def test_data_gaps_group_by_role_and_currency():
    _, _, _, blocked = _facts()
    gaps = data_gaps(blocked)
    jp = {(g["jurisdiction"], g["role"]): g["unlocks"] for g in gaps}
    assert jp[("JP", "unemployment_rate")] == ["sahm"]
    assert jp[("JP", "headline_cpi")] == ["phillips"]


def test_scorecard_zscore_and_regime():
    from render.steering.scorecard import _regime, _zscore

    class _Pt:
        def __init__(self, v): self.outputs = {"x": v}
    hist = [_Pt(v) for v in [1, 1, 1, 1, 1, 1, 1, 1, 5]]          # latest 5 is high vs a ~1 history
    lv, z = _zscore(hist, "x")
    assert lv == 5.0 and z is not None and z > 1.5               # elevated → positive z
    assert _zscore([_Pt(1)], "x") == (1.0, None)                 # too short → no z, level only

    class _P2:
        def __init__(self, cli, infl): self.outputs = {"leading_indicator": cli, "inflation_pct": infl}
    # hot cutoff is the jurisdiction's regime_hot_infl_pct (US = 2.5, from the vocab/calibration data)
    assert _regime(_P2(101, 3.0), "US") == "reflation"            # growing + hot
    assert _regime(_P2(101, 1.0), "US") == "goldilocks"          # growing + cool
    assert _regime(_P2(98, 3.0), "US") == "stagflation"          # slowing + hot
    assert _regime(_P2(98, 1.0), "US") == "slowdown"             # slowing + cool


def test_port_backlog_is_the_us_welded_models():
    uses, execin, generic, _ = _facts()
    back = port_backlog(generic, execin, ["US", "EU", "JP"])
    assert set(back) == {"taylor", "term_premium", "recession", "okun"}   # welded, US-only
    assert "sahm" not in back and "phillips" not in back                  # generic, reach EU
