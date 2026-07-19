"""Role-2 model selection — the deterministic validate step (P2b scope budget)."""
from render.selector.nodes import validate
from render.selector.state import Pick


def _lib(*ids):
    return [{"id": i} for i in ids]


def _picks(*ids):
    return [Pick(model_id=i, why=f"because {i}") for i in ids]


def test_scope_budget_trims_additions_beyond_the_floor_but_keeps_every_floor_pick():
    # floor = f1,f2; the LLM reaches for THREE additions — the exact v5 over-reach. Budget = 2.
    state = {
        "persona_id": "credit_investor",
        "library": _lib("f1", "f2", "a1", "a2", "a3"),
        "default_models": ["f1", "f2"],
        "picks": _picks("f1", "f2", "a1", "a2", "a3"),
        "add_budget": 2, "min_models": 3, "max_models": 5,
    }
    out = validate(state)
    assert out["selected"] == ["f1", "f2", "a1", "a2"]      # both floor kept, additions capped at 2
    assert "a3" not in out["selected"]
    assert any("scope budget" in r for r in out["rejected"])
    assert set(out["reasons"]) == set(out["selected"])      # reasons pruned to what shipped


def test_thin_persona_still_grows_within_budget():
    # commodity_analyst had 2 hardcoded and wrote the thinnest article — Role-2 must still enrich it.
    state = {
        "persona_id": "commodity_analyst",
        "library": _lib("f1", "f2", "a1", "a2"),
        "default_models": ["f1", "f2"],
        "picks": _picks("f1", "f2", "a1", "a2"),
        "add_budget": 2, "min_models": 3, "max_models": 5,
    }
    out = validate(state)
    assert out["selected"] == ["f1", "f2", "a1", "a2"]      # 2 → 4, richer, within budget
    assert not any("scope budget" in r for r in out["rejected"])


def test_hard_ceiling_holds_even_with_a_large_floor():
    state = {
        "persona_id": "central_bank_policymaker",
        "library": _lib("f1", "f2", "f3", "f4", "f5", "f6", "a1"),
        "default_models": ["f1", "f2", "f3", "f4", "f5", "f6"],
        "picks": _picks("f1", "f2", "f3", "f4", "f5", "f6", "a1"),
        "add_budget": 2, "min_models": 3, "max_models": 5,
    }
    out = validate(state)
    assert len(out["selected"]) == 5                        # never exceeds the hard ceiling
    assert "a1" not in out["selected"]                      # no room for additions once the floor fills it
