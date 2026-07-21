"""The jurisdiction-neutrality guard — the anti-regression net for "US is not the default".

Guards, not prose reminders, hold rules (memory: checks-must-not-convict-true-work / prompts-don't-hold-
rules-guards-do). This suite fails the build if:
  1. any pipeline-core function reintroduces a silent US default/fallback (`or "US"`, `= "US"` default,
     `.get("jurisdiction", "US")`);
  2. a shared renderer hardcodes US FRED series instead of resolving roles;
  3. the frame or persona_material stop RAISING on a missing jurisdiction (the silent-US path);
  4. the peer personas re-weld a hardcoded "The Fed" title instead of the {cb_title} token.

An explicit `instance="US"` at a CALL site is fine — that is a conscious peer choice. What is forbidden
is a hidden DEFAULT or FALLBACK that makes an unthreaded run quietly become US.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# The load-bearing pipeline files: an unthreaded jurisdiction here silently produces a US article.
CORE_FILES = [
    "render/graph_corpus.py",
    "render/model_store.py",
    "render/jurisdiction.py",
    "render/jurisdiction_facts.py",
    "render/article_graph/nodes.py",
    "render/article_graph/graph.py",
    "render/infographic/from_persona.py",
    "render/infographic/families/decision_brief.py",
    "render/infographic/families/regime_dashboard.py",
    "render/infographic/families/decomposition_hero.py",
    "render/infographic/families/cross_section_ladder.py",
]

# Hidden US default/fallback patterns — the exact mechanisms of the "regress every time" bug.
_FORBIDDEN = [
    re.compile(r'\bor\s+\[?["\']US["\']\]?'),                       # `or "US"` / `or ["US"]`
    re.compile(r'(instance|jurisdiction)\s*:\s*str\s*=\s*["\']US["\']'),   # `= "US"` default param
    re.compile(r'\.get\(\s*["\'](instance|jurisdiction)["\']\s*,\s*["\']US["\']'),  # .get(...,"US")
]

# US series ids that must not be hardcoded in a SHARED renderer (they belong to bindings, resolved by role).
_US_SERIES = re.compile(r'["\'](PCEPILFE|CPIAUCSL|UNRATE|FEDFUNDS|DGS10|DGS2|VIXCLS|ACMTP\d+)["\']')


def _strip_comments(src: str) -> str:
    """Drop full-line and trailing # comments so a documented example doesn't trip the scan."""
    out = []
    for line in src.splitlines():
        h = line.find("#")
        out.append(line if h < 0 else line[:h])
    return "\n".join(out)


@pytest.mark.parametrize("rel", CORE_FILES)
def test_no_hidden_us_default_in_core(rel):
    code = _strip_comments((REPO / rel).read_text())
    for pat in _FORBIDDEN:
        m = pat.search(code)
        assert not m, f"{rel}: hidden US default/fallback `{m.group()}` — thread the jurisdiction instead"


def test_shared_renderers_dont_hardcode_us_series():
    for rel in ("render/infographic/families/regime_dashboard.py",
                "render/infographic/families/decision_brief.py"):
        code = _strip_comments((REPO / rel).read_text())
        m = _US_SERIES.search(code)
        assert not m, f"{rel}: hardcoded US series {m.group()} in a shared renderer — resolve via a role"


def test_frame_raises_never_falls_back_to_us():
    from render.jurisdiction import frame
    assert frame("EU")["cb_title"] == "The ECB"
    assert frame("GB")["central_bank"] == "Bank of England"
    with pytest.raises(KeyError):
        frame("ZZ")                       # unknown jurisdiction must raise, NOT return US


def test_frame_tokens_fill_per_jurisdiction():
    from render.jurisdiction import fill_frame_tokens
    assert fill_frame_tokens("{cb_title} today", "EU") == "The ECB today"
    assert fill_frame_tokens("{cb_title} today", "JP") == "The Bank of Japan today"
    # a {model.output} token (with a dot) must survive the frame fill untouched
    assert fill_frame_tokens("{reaction_function.policy}% via {cb_the}", "GB") == \
        "{reaction_function.policy}% via the Bank of England"


def test_persona_material_requires_instance():
    from render.infographic.from_persona import persona_material
    sig = inspect.signature(persona_material)
    inst = sig.parameters["instance"]
    assert inst.default is inspect.Parameter.empty, \
        "persona_material.instance must be REQUIRED — a default reintroduces the silent-US path"


def test_build_article_full_requires_jurisdiction():
    from render.writer import build_article_full
    sig = inspect.signature(build_article_full)
    assert sig.parameters["jurisdiction"].default is inspect.Parameter.empty, \
        "build_article_full.jurisdiction must be REQUIRED — the caller must choose the economy"


def test_peer_personas_use_templated_title_not_hardcoded_fed():
    import yaml
    personas = yaml.safe_load((REPO / "catalog/graph/personas.yaml").read_text())["personas"]
    cb = personas["central_bank_policymaker"]
    assert "{cb_title}" in cb["title"], "central_bank_policymaker title must be jurisdiction-templated"
    assert "the Fed" not in cb.get("summary_template", ""), \
        "central_bank_policymaker summary must not hardcode 'the Fed' — use {cb_the}"


# ── the vocabulary + rules are DATA, not hardcoded Python (the soft-coding contract) ──────────────

def test_vocab_and_rules_are_data_not_hardcoded_python():
    """The prose layer must live in the jurisdiction DATA, not in Python structures — so adding a
    jurisdiction is a YAML+re-seed change, not a code edit."""
    jur = (REPO / "render/jurisdiction.py").read_text()
    assert "_VOCAB" not in jur, "render/jurisdiction.py must not hold a _VOCAB dict — read vocab from data"
    sc = _strip_comments((REPO / "render/steering/scorecard.py").read_text())
    assert "_CB_SHORT =" not in sc, "scorecard must not hardcode _CB_SHORT — read cb_short from data"
    wr = _strip_comments((REPO / "render/writer.py").read_text())
    assert "core PCE" not in wr and "civilian unemployment" not in wr, \
        "writer must not hold a US-term blacklist — derive forbidden terms from the vocab data"


def test_forbidden_terms_derived_and_peer_symmetric():
    from render.writer import _forbidden_terms
    eu = _forbidden_terms("EU")
    assert "the Fed" in eu and "FOMC" in eu, "EU must forbid US-branded terms"
    assert "the ECB" not in eu and "The ECB" not in eu, "EU must not forbid its OWN terms"
    us = _forbidden_terms("US")
    assert "the ECB" in us, "US must forbid EU-branded terms too — peer-symmetric, not US-privileged"
    assert "CPI inflation" not in us, "US uses 'CPI inflation' — never forbid a term this economy uses"


def test_calibration_is_per_jurisdiction():
    from render.graph_corpus import _load_model
    us = _load_model("reaction_function", "US")["spec"].params
    jp = _load_model("reaction_function", "JP")["spec"].params
    assert us["r_star_pct"] == 0.7 and jp["r_star_pct"] == 0.0, \
        "reaction_function must read the article jurisdiction's r*, not one global constant"


@pytest.mark.neo4j
def test_neo4j_and_catalog_readers_agree():
    """Parity: the live-graph reader and the catalog reader return the same facts after a seed."""
    from render import jurisdiction_facts as jf
    import os as _os
    jf.reset(); _os.environ["HORIZON3_JUR_SOURCE"] = "catalog"
    cat = jf.all_facts()
    jf.reset(); _os.environ["HORIZON3_JUR_SOURCE"] = "neo4j"
    try:
        neo = jf.all_facts()
    except Exception as exc:
        pytest.skip(f"no seeded Neo4j: {exc}")
    finally:
        jf.reset(); _os.environ["HORIZON3_JUR_SOURCE"] = "catalog"
    assert set(cat) == set(neo)
    for j in cat:
        assert cat[j]["vocab"] == neo[j]["vocab"], f"{j} vocab differs between readers"
        assert cat[j]["calibration"] == neo[j]["calibration"], f"{j} calibration differs"
