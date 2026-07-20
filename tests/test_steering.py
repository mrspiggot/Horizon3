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


def test_port_backlog_is_the_us_welded_models():
    uses, execin, generic, _ = _facts()
    back = port_backlog(generic, execin, ["US", "EU", "JP"])
    assert set(back) == {"taylor", "term_premium", "recession", "okun"}   # welded, US-only
    assert "sahm" not in back and "phillips" not in back                  # generic, reach EU
