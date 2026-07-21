"""The jurisdiction frame — the per-instance vocabulary a prompt/renderer uses so an article speaks in its
own economy's terms and NEVER says "the Fed" on a euro-area piece.

The vocabulary is DATA now: it lives in the Neo4j spine (seeded from catalog/jurisdictions.yaml) and is
read at runtime via `render.jurisdiction_facts`. Adding a jurisdiction is a data change — no edit here.
`frame()` RAISES on an unknown instance (never US); it does not cache (the provider already does).
"""
from __future__ import annotations

from . import jurisdiction_facts


def frame(instance: str) -> dict[str, str]:
    """The full vocabulary for one jurisdiction, from the graph. RAISES on an unknown instance — never US."""
    f = jurisdiction_facts.facts(instance)       # KeyError on unknown; RuntimeError if the spine is unseeded
    v = f["vocab"]
    return {
        "instance": instance,
        "central_bank": f["central_bank"],
        "ccy": f["ccy"],
        "cb_the": v.get("cb_the", f["central_bank"]),
        "cb_title": v.get("cb_title", f["central_bank"]),
        "cb_short": v.get("cb_short", f["central_bank"]),
        "policy_rate": v.get("policy_rate", "the policy rate"),
        "price_index": v.get("price_index", "CPI inflation"),
        "benchmark": v.get("benchmark", "the 10-year government bond"),
        "govt": v.get("govt", "government bonds"),
    }


def fill_frame_tokens(text: str, instance: str) -> str:
    """Substitute {central_bank}/{cb_the}/{cb_title}/{cb_short}/{policy_rate}/{price_index}/{benchmark}/
    {govt}/{ccy} tokens with the instance's vocabulary. Leaves {model_id.output} tokens (which carry a dot)
    untouched — uses str.replace, not .format, precisely so the dotted tokens survive."""
    f = frame(instance)
    for k, val in f.items():
        text = text.replace("{" + k + "}", str(val))
    return text
