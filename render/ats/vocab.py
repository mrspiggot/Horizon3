"""The trigger→grounding vocabulary — derived from the catalog, not hardcoded.

A trigger names a domain ("inflation"), a jurisdiction ("EU"), or a news theme. To ground an article we
must resolve that to a persona + model that our estate can execute. This module loads the catalog's own
vocabulary — every `catalog/graph/<model>.yaml` header carries `family:` + `persona:`; personas.yaml
lists each persona's models; jurisdictions.yaml lists the central banks — and exposes the crosswalk. The
one authored bridge is `DOMAIN_TO_PERSONA` (events.yaml's `domain` vocab → graph personas); everything
else is read from files so a catalog change flows through.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CATALOG = Path(__file__).resolve().parents[2] / "catalog"
_GRAPH = _CATALOG / "graph"

# The one authored bridge: events.yaml `domain` → the graph personas that speak to it. Kept small and
# explicit; validated against the loaded personas at import via _check().
DOMAIN_TO_PERSONA: dict[str, list[str]] = {
    "rates": ["central_bank_policymaker", "macro_rates_trader"],
    "inflation": ["central_bank_policymaker", "economist_forecaster"],
    "growth": ["economist_forecaster", "central_bank_policymaker"],
    "credit": ["credit_investor", "corporate_treasurer"],
    "vol": ["volatility_trader"],
    "equity": ["equity_multiasset_pm"],
    "cross_asset": ["equity_multiasset_pm"],
    "commodity": ["commodity_analyst"],
    "crypto": ["volatility_trader"],                         # nearest groundable persona
}


@lru_cache(maxsize=1)
def personas() -> dict:
    """{persona_id: {name, decision, title, models, ...}} — the render-ready persona specs."""
    return yaml.safe_load((_GRAPH / "personas.yaml").read_text())["personas"]


@lru_cache(maxsize=1)
def _model_headers() -> dict[str, dict]:
    """{model_id: {family, persona}} from each graph model YAML header."""
    out = {}
    for f in _GRAPH.glob("*.yaml"):
        if f.name == "personas.yaml":
            continue
        try:
            d = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue
        mid = d.get("model_id") or f.stem
        out[mid] = {"family": d.get("family", ""), "persona": d.get("persona", "")}
    return out


@lru_cache(maxsize=1)
def jurisdictions() -> list[dict]:
    """[{id, central_bank, ccy}] from jurisdictions.yaml."""
    j = yaml.safe_load((_CATALOG / "jurisdictions.yaml").read_text())
    return [{"id": x["id"], "central_bank": x.get("central_bank", ""), "ccy": x.get("ccy", "")}
            for x in j.get("jurisdictions", [])]


def ccy_for(jur_id: str) -> str:
    return next((j["ccy"] for j in jurisdictions() if j["id"] == jur_id), "")


def central_bank_for(jur_id: str) -> str:
    return next((j["central_bank"] for j in jurisdictions() if j["id"] == jur_id), "")


@lru_cache(maxsize=1)
def _jurisdictions_full() -> list[dict]:
    return yaml.safe_load((_CATALOG / "jurisdictions.yaml").read_text()).get("jurisdictions", [])


def jurisdiction_vocab(jur_id: str) -> dict:
    """The jurisdiction's own naming vocab ({cb_the, price_index, benchmark, ...}) — the source of
    data-driven, jurisdiction-aware prose. No jurisdiction is a default; unknown ⇒ {}."""
    return next((x.get("vocab", {}) for x in _jurisdictions_full() if x.get("id") == jur_id), {})


def models_for_persona(persona_id: str) -> list[str]:
    return list(personas().get(persona_id, {}).get("models", []))


def personas_for_domain(domain: str) -> list[str]:
    return [p for p in DOMAIN_TO_PERSONA.get(domain or "", []) if p in personas()]


def is_valid_persona(persona_id: str) -> bool:
    return persona_id in personas()


PERSONA_IDS = tuple(personas().keys())
DOMAINS = tuple(DOMAIN_TO_PERSONA.keys())
JURISDICTION_IDS = tuple(j["id"] for j in jurisdictions())
