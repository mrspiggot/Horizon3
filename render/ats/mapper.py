"""Map a candidate trigger to the persona + model that would ground its article.

Deterministic where we can (a `domain` → the crosswalk in vocab.py → the persona's anchor model, reusing
article.MODEL_PICK); an LLM classifier CONSTRAINED to the existing family/domain/persona vocabulary for
free-text triggers (zeitgeist headlines, the owner's paragraph). The classifier can only choose labels
that already exist — it never invents a topic — and a low-confidence result is dropped, not force-fit.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import vocab
from .schema import CandidateTrigger


def _anchor_model(persona: str) -> list[str]:
    from ..article import MODEL_PICK
    m = MODEL_PICK.get(persona)
    return [m] if m else vocab.models_for_persona(persona)[:1]


class _Classification(BaseModel):
    domain: Literal["rates", "inflation", "growth", "credit", "vol", "equity", "cross_asset",
                    "commodity", "crypto", "none"] = Field(description="the closest existing domain, or 'none' if none fits")
    persona: Literal["central_bank_policymaker", "macro_rates_trader", "volatility_trader",
                     "credit_investor", "equity_multiasset_pm", "commodity_analyst",
                     "corporate_treasurer", "economist_forecaster", "none"] = Field(
        description="the persona best placed to ground an article on this, or 'none'")
    confidence: float = Field(description="0..1 confidence that this maps cleanly onto our estate")


def _classify(text: str) -> _Classification | None:
    try:
        from ..studio.llm import get_llm
        llm = get_llm(max_tokens=512).with_structured_output(_Classification)
        return llm.invoke(
            "You route a financial news headline / commission to the ONE persona in our estate best "
            "placed to write a model-grounded article on it. Choose ONLY from the given labels; if "
            "nothing fits, return 'none'. Personas: central bank policymaker (Taylor-rule/policy), "
            "macro rates trader (term premium/curve), volatility trader (VIX/GARCH/VRP), credit "
            "investor (spreads/default/EBP), equity/multi-asset PM (financial conditions/ERP/gold), "
            "commodity analyst (energy complex), corporate treasurer (funding cost), economist/"
            f"forecaster (labour/recession).\n\nHeadline / request: {text}")
    except Exception:
        return None


def map_candidate(cand: CandidateTrigger, *, min_conf: float = 0.45) -> CandidateTrigger:
    """Fill personas + models. Returns the same candidate (personas empty ⇒ drop it downstream)."""
    if cand.personas:                                        # standing pieces arrive pre-mapped
        if not cand.models:
            cand.models = _anchor_model(cand.persona)
        return cand

    if cand.domain and cand.domain != "crypto":             # deterministic crosswalk
        personas = vocab.personas_for_domain(cand.domain)
        if personas:
            cand.personas = personas[:2]
            cand.models = _anchor_model(cand.personas[0])
            return cand

    # free-text / crypto / unresolved → the constrained LLM classifier
    cls = _classify(f"{cand.title}. {cand.rationale}")
    if cls and cls.persona != "none" and cls.confidence >= min_conf and vocab.is_valid_persona(cls.persona):
        cand.personas = [cls.persona]
        cand.domain = cand.domain or (cls.domain if cls.domain != "none" else None)
        cand.models = _anchor_model(cls.persona)
    return cand


def map_all(cands: list[CandidateTrigger]) -> list[CandidateTrigger]:
    return [map_candidate(c) for c in cands]
