"""The jurisdiction frame — the per-instance vocabulary every renderer and prompt needs so an article
speaks in its own economy's terms and NEVER says "the Fed" on a euro-area piece.

US is one instance among peers (US/EU/GB/JP/…), never the default. `frame()` RAISES on an unknown
instance rather than silently returning US — that silent fallback is the exact regression this module
exists to end. The central-bank name and currency are read from the binding SoT
(catalog/jurisdictions.yaml); the label vocabulary (what this economy calls its policy rate, its price
index, its benchmark bond) lives here because it is prose, not data.
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

_JUR_YAML = Path(__file__).resolve().parent.parent / "catalog" / "jurisdictions.yaml"

# The words each economy uses. `cb_the` is the lower-case running-prose form ("the Fed"); `cb_title`
# is the headline/title-case form ("The Fed"). Keep these peer-symmetric — no jurisdiction is special.
_VOCAB: dict[str, dict[str, str]] = {
    "US": {"cb_the": "the Fed",  "cb_title": "The Fed",
           "policy_rate": "the federal funds rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year Treasury", "govt": "Treasuries"},
    "EU": {"cb_the": "the ECB",  "cb_title": "The ECB",
           "policy_rate": "the deposit rate", "price_index": "HICP inflation",
           "benchmark": "the 10-year Bund", "govt": "Bunds"},
    "GB": {"cb_the": "the Bank of England", "cb_title": "The Bank of England",
           "policy_rate": "Bank Rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year gilt", "govt": "gilts"},
    "JP": {"cb_the": "the Bank of Japan", "cb_title": "The Bank of Japan",
           "policy_rate": "the policy rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year JGB", "govt": "JGBs"},
    "CH": {"cb_the": "the SNB", "cb_title": "The SNB",
           "policy_rate": "the SNB policy rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year Confederation bond", "govt": "Swiss govvies"},
    "CA": {"cb_the": "the Bank of Canada", "cb_title": "The Bank of Canada",
           "policy_rate": "the overnight rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year Canada", "govt": "Canadas"},
    "AU": {"cb_the": "the RBA", "cb_title": "The RBA",
           "policy_rate": "the cash rate", "price_index": "CPI inflation",
           "benchmark": "the 10-year ACGB", "govt": "ACGBs"},
}


@functools.lru_cache(maxsize=1)
def _sot() -> dict[str, dict[str, str]]:
    """central_bank + ccy per jurisdiction, from the binding source of truth."""
    d = yaml.safe_load(_JUR_YAML.read_text())
    return {j["id"]: {"central_bank": j.get("central_bank", j["id"]), "ccy": j.get("ccy", "")}
            for j in d.get("jurisdictions", [])}


@functools.lru_cache(maxsize=16)
def frame(instance: str) -> dict[str, str]:
    """The full vocabulary for one jurisdiction. RAISES KeyError on an unknown instance — never US."""
    sot = _sot()
    if instance not in sot and instance not in _VOCAB:
        raise KeyError(f"no jurisdiction frame for {instance!r} — refusing to default to US "
                       f"(known: {sorted(set(sot) | set(_VOCAB))})")
    s = sot.get(instance, {})
    v = _VOCAB.get(instance, {})
    cb = s.get("central_bank") or v.get("cb_title") or instance
    return {
        "instance": instance,
        "central_bank": cb,
        "ccy": s.get("ccy", ""),
        "cb_the": v.get("cb_the", cb),
        "cb_title": v.get("cb_title", cb),
        "policy_rate": v.get("policy_rate", "the policy rate"),
        "price_index": v.get("price_index", "CPI inflation"),
        "benchmark": v.get("benchmark", "the 10-year government bond"),
        "govt": v.get("govt", "government bonds"),
    }


def fill_frame_tokens(text: str, instance: str) -> str:
    """Substitute {central_bank}/{cb_the}/{cb_title}/{policy_rate}/{price_index}/{benchmark}/{ccy}
    tokens in a template with the instance's vocabulary. Leaves {model_id.output} tokens (which carry
    a dot) untouched, so it composes with the numeric summary-template filler. Uses str.replace, not
    .format, precisely so the dotted tokens survive."""
    f = frame(instance)
    for k, val in f.items():
        text = text.replace("{" + k + "}", str(val))
    return text
