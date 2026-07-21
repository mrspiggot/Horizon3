"""The runtime source of jurisdiction facts — vocabulary, calibration, role bindings.

Owner decision: **Neo4j is the live runtime source.** `catalog/jurisdictions.yaml` is the authoring/seed
source; at render time the app QUERIES the seeded graph so that adding a jurisdiction is a pure DATA change
(edit the YAML + re-seed) with no Python edit. There is deliberately NO silent fallback to US and, in
`neo4j` mode, no silent fallback to the YAML — a missing/unseeded jurisdiction RAISES, because a silent
fallback is exactly the default-to-US anti-pattern this layer exists to kill.

Test/offline mode: set `HORIZON3_JUR_SOURCE=catalog` to read the same seed YAML through the *identical*
normaliser (so the two readers converge — a parity test guards it). `tests/conftest.py` sets this so the
suite runs with no live graph. Production defaults to `neo4j`.
"""
from __future__ import annotations

import atexit
import functools
import json
import os
from pathlib import Path

import yaml

_JUR_YAML = Path(__file__).resolve().parent.parent / "catalog" / "jurisdictions.yaml"
_CATALOG = "horizon3"

_VOCAB_KEYS = ("cb_the", "cb_title", "cb_short", "policy_rate", "price_index", "benchmark", "govt")
_CALIB_KEYS = ("r_star_pct", "inflation_target_pct", "phillips_u_star_pct",
               "phillips_hot_infl_pct", "regime_hot_infl_pct")

_DRIVER = None


def brand_terms(vocab: dict) -> list[str]:
    """The branded terms a FOREIGN article must never use — this economy's institution/measure/benchmark
    names plus its aliases. The neutrality rules are DERIVED from this, so there is no hardcoded blacklist."""
    terms = [vocab.get(k, "") for k in _VOCAB_KEYS] + list(vocab.get("aliases", []) or [])
    return sorted({t for t in terms if t})


def _source() -> str:
    return os.getenv("HORIZON3_JUR_SOURCE", "neo4j").lower()


def _driver():
    global _DRIVER
    if _DRIVER is None:
        from neo4j import GraphDatabase   # lazy — catalog mode never needs neo4j installed/reachable
        _DRIVER = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7688"),
            auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "devpassword")))
        atexit.register(_DRIVER.close)
    return _DRIVER


def _normalize(id_, central_bank, ccy, scope, order, vocab, calibration, bindings) -> dict:
    """The single shape both readers return, so neo4j and catalog modes converge by construction."""
    return {
        "id": id_, "central_bank": central_bank or id_, "ccy": ccy or "", "scope": scope or "",
        "order": order if order is not None else 999,
        "vocab": vocab or {}, "calibration": calibration or {},
        "bindings": {r: (ref, src) for r, (ref, src) in (bindings or {}).items() if r and ref},
        "meta": {"id": id_, "central_bank": central_bank or id_, "ccy": ccy or "", "scope": scope or ""},
    }


def _from_catalog(catalog: str) -> dict:
    d = yaml.safe_load(_JUR_YAML.read_text())
    out = {}
    for j in d.get("jurisdictions", []):
        binds = {}
        for role, b in (j.get("bindings") or {}).items():
            if isinstance(b, dict) and b.get("ref"):
                binds[role] = (b["ref"], b.get("source"))
        out[j["id"]] = _normalize(j["id"], j.get("central_bank"), j.get("ccy"), j.get("scope"),
                                  j.get("display_order"), j.get("vocab") or {}, j.get("calibration") or {},
                                  binds)
    return out


def _from_neo4j(catalog: str) -> dict:
    q = """
    MATCH (j:Jurisdiction {catalog:$cat})
    OPTIONAL MATCH (r:Role {catalog:$cat})-[b:BOUND_TO {jurisdiction:j.id}]->(d:DataSeries {catalog:$cat})
    RETURN j.id AS id, j.central_bank AS central_bank, j.ccy AS ccy, j.scope AS scope,
           j.display_order AS ord, j.vocab AS vocab, j.calibration AS calibration,
           collect({role:r.name, ref:d.ref, source:coalesce(b.source, d.source)}) AS bindings
    ORDER BY j.display_order, j.id
    """
    try:
        with _driver().session() as s:
            rows = s.run(q, cat=catalog).data()
    except Exception as exc:
        raise RuntimeError(
            f"jurisdiction facts require a seeded Neo4j spine ({os.getenv('NEO4J_URI', 'bolt://localhost:7688')}). "
            f"Run `python scripts/seed_spine.py`, or set HORIZON3_JUR_SOURCE=catalog for offline/test. "
            f"Cause: {type(exc).__name__}: {exc}") from exc
    if not rows:
        raise RuntimeError("Neo4j has no Jurisdiction nodes for catalog "
                           f"{catalog!r} — run `python scripts/seed_spine.py`.")
    out = {}
    for r in rows:
        # A malformed/absent vocab or calibration prop must RAISE (unseeded node), never yield {} silently.
        vocab = json.loads(r["vocab"]) if r["vocab"] is not None else None
        calib = json.loads(r["calibration"]) if r["calibration"] is not None else None
        if not vocab or not calib:
            raise RuntimeError(f"Jurisdiction {r['id']!r} is missing vocab/calibration in the spine — "
                               f"re-seed after adding them to jurisdictions.yaml.")
        binds = {x["role"]: (x["ref"], x["source"]) for x in (r["bindings"] or []) if x.get("role") and x.get("ref")}
        out[r["id"]] = _normalize(r["id"], r["central_bank"], r["ccy"], r["scope"], r["ord"],
                                  vocab, calib, binds)
    return out


@functools.lru_cache(maxsize=4)
def all_facts(catalog: str = _CATALOG) -> dict:
    """{instance_id: normalized facts} for every jurisdiction, queried once per process and cached."""
    return _from_catalog(catalog) if _source() == "catalog" else _from_neo4j(catalog)


def facts(instance: str, catalog: str = _CATALOG) -> dict:
    """Facts for one jurisdiction. RAISES KeyError on an unknown instance — never defaults to US."""
    af = all_facts(catalog)
    if instance not in af:
        raise KeyError(f"no jurisdiction facts for {instance!r} — refusing to default to US "
                       f"(known: {sorted(af)})")
    return af[instance]


def reset() -> None:
    """Invalidate the process cache (call at batch start after a re-seed) and drop the driver."""
    all_facts.cache_clear()
    global _DRIVER
    if _DRIVER is not None:
        _DRIVER.close()
        _DRIVER = None
