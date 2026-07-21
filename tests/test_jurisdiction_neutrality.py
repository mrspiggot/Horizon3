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
