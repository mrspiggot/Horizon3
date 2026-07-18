"""The reconciliation stage: charts, prose, dashboard and numbers as projections of one state.

These lock in the four fixes that took the v2 batch off a converged ~6.8:
  A  charts bind to the SECTION whose prose reads them, surviving redraft reorder/expansion;
  B  every NAMED EXHIBIT the prose promises is built — and topic-mentions do not stuff the article;
  C  the dashboard's thesis/read/tiles come from the finished article, not the static template;
  D  a concept emitted by two models collapses to ONE citable number everywhere.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from render.infographic.schema import NumberObject  # noqa: E402


def _N(key, val, unit, fmt="{:.2f}"):
    return NumberObject(name=key, value=val, unit=unit, fmt=fmt, source=key, as_of="2026-07-17")


# ── Pass 1 — "one figure, once" (number-rendering guard) ──────────────────────────────────────────
def test_one_figure_once_collapses_doubles_but_spares_distinct_numbers():
    from render.writer import _one_figure_once
    toks = {"n0": _N("n0", 0.18, "pp", "{:+.2f}"), "n1": _N("n1", 5.31, "%"), "n2": _N("n2", 1.06, "%")}
    # doubled token, and a worded round approximation run into its own numeral
    assert _one_figure_once("reads +0.18pp +0.18pp, faintly", toks) == "reads +0.18pp, faintly"
    assert _one_figure_once("a rate above five percent 5.31%;", toks) == "a rate above 5.31%;"
    assert _one_figure_once("r* is only about one percent 1.06%.", toks) == "r* is only about 1.06%."
    # must NOT touch two genuinely distinct adjacent figures, nor a lone worded approximation
    assert _one_figure_once("rose from 1.06% to 5.31%", toks) == "rose from 1.06% to 5.31%"
    assert _one_figure_once("an r* of around one percent anchors it", toks) == "an r* of around one percent anchors it"


# ── Pass 1 — one concept once, extended (cross-model numbers + subset charts) ──────────────────────
def test_concept_registry_merges_same_concept_different_field_names():
    from render.infographic.from_persona import _concept_registry
    numbers = {"funding_quality.ig_all_in_pct": _N("funding_quality.ig_all_in_pct", 5.86, "%"),
               "funding_cost.all_in_pct": _N("funding_cost.all_in_pct", 5.05, "%"),
               "funding_quality.hy_all_in_pct": _N("funding_quality.hy_all_in_pct", 8.10, "%")}
    meanings = {"funding_quality.ig_all_in_pct": "all-in IG funding cost",
                "funding_cost.all_in_pct": "all-in fixed IG funding cost",
                "funding_quality.hy_all_in_pct": "all-in HY funding cost"}
    runs = {m.split(".")[0]: {"meta": {"name": m}, "history": [0] * 300} for m in numbers}
    _c, canon = _concept_registry(numbers, meanings, template_keys=set(), runs=runs)
    assert canon["funding_quality.ig_all_in_pct"] == canon["funding_cost.all_in_pct"]  # 5.86≡5.05
    assert canon["funding_quality.hy_all_in_pct"] != canon["funding_quality.ig_all_in_pct"]  # IG≠HY


def test_chart_dedup_collapses_subset_within_model_keeps_other_models():
    from render.writer import _dedup_by_concept
    gz = frozenset({"gz_spread", "expected_default", "excess_bond_premium"})
    ci = {"GZ decomposition": {"model_id": "credit_ebp", "refs": gz},
          "The excess bond premium": {"model_id": "credit_ebp", "refs": frozenset({"excess_bond_premium"})},
          "Decomposition, again": {"model_id": "credit_ebp", "refs": gz},
          "Quality ladder": {"model_id": "ladder", "refs": frozenset({"ig_oas", "hy_oas", "em_oas"})}}
    out = _dedup_by_concept(list(ci), ci)
    assert "The excess bond premium" not in out          # subsumed by the decomposition
    assert sum("ecomposition" in c for c in out) == 1     # one decomposition, not two
    assert "Quality ladder" in out                        # a different model is untouched


# ── Pass 1 — dashboard badge suppressed only on a clear contradiction with the body ────────────────
def test_badge_suppressed_only_on_clear_contradiction():
    from render.infographic.families.regime_dashboard import _badge_contradicts_body
    body = ("Inflation has fallen to 2.39%, near the bottom of its recent range; its momentum has bled "
            "out and decelerated hard. The labour market is still tight and vacancies remain high.")
    assert _badge_contradicts_body("CPI", "elevated", "rising", body) is True       # CPI↔inflation synonym
    assert _badge_contradicts_body("Vacancy rate", "elevated", "rising", body) is False  # body agrees → keep
    assert _badge_contradicts_body("CPI", "elevated", "rising", "cpi feeds the model") is False  # ambiguous


# ── D — one concept → one number ──────────────────────────────────────────────────────────────────
def test_concept_registry_collapses_same_concept_keeps_distinct_apart():
    from render.infographic.from_persona import _concept_registry
    numbers = {
        "variance_risk_premium.implied_vol_pct": _N("variance_risk_premium.implied_vol_pct", 15.57, "%"),
        "garch_volatility.implied_vol_pct": _N("garch_volatility.implied_vol_pct", 16.73, "%"),
        "funding_quality.ig_all_in_pct": _N("funding_quality.ig_all_in_pct", 5.86, "%"),
        "funding_quality.hy_all_in_pct": _N("funding_quality.hy_all_in_pct", 8.10, "%"),
    }
    meanings = {k: "" for k in numbers}
    runs = {"variance_risk_premium": {"meta": {"name": "VRP"}, "history": [0] * 252},
            "garch_volatility": {"meta": {"name": "GARCH"}, "history": [0] * 100},
            "funding_quality": {"meta": {"name": "Funding"}, "history": [0] * 500}}
    _concepts, canon = _concept_registry(numbers, meanings, template_keys=set(), runs=runs)
    iv = [k for k in numbers if "implied_vol" in k]
    assert canon[iv[0]] == canon[iv[1]]                               # two implied-vols → one
    assert canon[iv[0]] == "variance_risk_premium.implied_vol_pct"    # the longer-history model wins
    assert canon["funding_quality.ig_all_in_pct"] != canon["funding_quality.hy_all_in_pct"]  # IG≠HY


# ── A — semantic placement, robust to redraft drift ───────────────────────────────────────────────
def _cb_fixture():
    from render.writer import Outline, SectionPlan, SectionDraft
    outline = Outline(headline="H", standfirst="s", pivot="p", open_close="o", sections=[
        SectionPlan(heading="The real policy rate", thesis="t", model_id="real_rate",
                    chart_ids=["Real rate vs r*"]),
        SectionPlan(heading="Labour-market tightness", thesis="t", model_id="beveridge_curve",
                    chart_ids=["V/U tightness"]),
        SectionPlan(heading="The term spread", thesis="t", model_id="term_spread",
                    chart_ids=["Term spread 10y-3m"]),
    ])
    # writer REORDERS + RENAMES the sections and adds Phillips-curve prose
    filled = [
        SectionDraft(heading="Labour-market tightness and the Beveridge curve",
                     prose="the beveridge curve jumped outward; the phillips curve is the punchline."),
        SectionDraft(heading="By the real-rate yardstick", prose="the real_rate stance drained to neutral"),
        SectionDraft(heading="What the market prices — the term spread", prose="term_spread positive again"),
    ]
    ci = {
        "Real rate vs r*": {"model_id": "real_rate", "insight": ""},
        "V/U tightness": {"model_id": "beveridge_curve", "insight": ""},
        "Term spread 10y-3m": {"model_id": "term_spread", "insight": ""},
        "The Phillips curve (unemployment vs inflation)": {"model_id": "phillips_curve", "insight": ""},
    }
    return outline, filled, ci


def test_charts_bind_to_the_section_that_reads_them_after_reorder():
    from render.writer import _bind_sections, _place_charts
    outline, filled, ci = _cb_fixture()
    bindings = _bind_sections(outline, filled, ci)
    _place_charts(bindings, ci)
    for sec, b in zip(filled, bindings):
        sec.chart_ids = list(b.chart_ids)
    labour = next(s for s in filled if "Labour" in s.heading)
    realr = next(s for s in filled if "yardstick" in s.heading)
    assert "V/U tightness" in labour.chart_ids          # not one section off, as the old i%len did
    assert "Real rate vs r*" in realr.chart_ids


# ── B — completeness, high precision ──────────────────────────────────────────────────────────────
def test_named_exhibit_is_built_but_topic_mention_is_not():
    from render.writer import _bind_sections, _reconcile_prose_charts, _place_charts, _prose_names
    outline, filled, ci = _cb_fixture()
    full_text = " ".join(s.prose for s in filled)
    bindings = _bind_sections(outline, filled, ci)
    _reconcile_prose_charts(full_text, bindings, {"chart_index": ci}, conn=None, mat={"id": "cb", "runs": {}})
    _place_charts(bindings, ci)
    for sec, b in zip(filled, bindings):
        sec.chart_ids = list(b.chart_ids)
    built = {c for s in filled for c in s.chart_ids}
    assert "The Phillips curve (unemployment vs inflation)" in built    # promised → built
    # a chart whose TOPIC is discussed but which is not named as an exhibit must NOT be pulled
    assert not _prose_names("Reaction function — Taylor vs actual", {"model_id": "reaction_function"},
                            "the reaction function shows the fed is behind and the output gap is wide")


# ── C — dashboard from the finished article ───────────────────────────────────────────────────────
def test_dashboard_reads_the_article_and_falls_back_to_template():
    from render.infographic.from_persona import dashboard_thesis, dashboard_read, dashboard_tile_keys
    numbers = {"m.cpi_pct": _N("m.cpi_pct", 2.39, "%"), "m.taylor_pct": _N("m.taylor_pct", 5.31, "%"),
               "m.stance_pp": _N("m.stance_pp", 0.18, "pp"), "m.prob": _N("m.prob", 0.16, "")}
    mat = {"p": {"summary_template": "Template thesis. Stale template read."}, "numbers": numbers,
           "salient": ["m.cpi_pct", "m.taylor_pct", "m.stance_pp", "m.prob"], "canon": {}}
    article = {"exec_summary": "The Fed is behind its own rule. Inflation has fallen. "
                               "The gap is the bet, and it cannot be hedged both ways.",
               "cited_keys": ["m.stance_pp", "m.cpi_pct"]}
    assert "rule" in dashboard_thesis(mat, article).lower()
    assert "hedged" in dashboard_read(mat, article).lower()
    tk = dashboard_tile_keys(mat, article, n=4)
    assert tk[:2] == ["m.stance_pp", "m.cpi_pct"]            # the numbers the PROSE cited lead the tiles
    assert "template" in dashboard_thesis(mat, None).lower()  # clean fallback when no article
