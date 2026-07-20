"""Enumerate the grounded analysis space from the spine — the graph's answer to "what can we write?".

Pure functions operate on plain facts pulled from Neo4j (so they unit-test without a database):
  uses     : {decision_maker_id: [model_ids]}          — (:DecisionMaker)-[:USES]->(:Model)
  execin   : {(model_id, jurisdiction_id)}             — (:Model)-[:EXECUTABLE_IN]->(:Jurisdiction), PROVEN
  generic  : {model_id: bool}                          — role-based (portable) vs US-welded
  blocked  : {(model_id, jur_id): [missing_role, …]}   — (:Model)-[:NEEDS]->(:Role)-[:MISSING_IN]->(:J)

`enumerate_analyses` yields the article set; `data_gaps` and `port_backlog` yield the two kinds of "what
would unlock more" — a data-sourcing target (a role with no series in a currency) vs a porting target (a
US-welded model that must be rewritten to roles before it can leave the US).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Analysis:
    decision_maker: str
    jurisdiction: str
    decision: str
    grounded_models: list[str]
    total_models: int
    groundable: bool
    missing_models: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.grounded_models)


def enumerate_analyses(uses: dict, execin: set, jur_ids: list[str], decisions: dict | None = None,
                       *, min_models: int = 3) -> list[Analysis]:
    """Every (decision-maker × currency) the graph can ground, most-covered first. `groundable` is True
    when at least `min_models` of that decision-maker's models are proven EXECUTABLE_IN the currency —
    below the floor it is a near-miss (still reported, so the gap to close is visible)."""
    decisions = decisions or {}
    out: list[Analysis] = []
    for dm, models in uses.items():
        for jid in jur_ids:
            grounded = [m for m in models if (m, jid) in execin]
            out.append(Analysis(
                decision_maker=dm, jurisdiction=jid, decision=decisions.get(dm, ""),
                grounded_models=grounded, total_models=len(models),
                groundable=len(grounded) >= min_models,
                missing_models=[m for m in models if (m, jid) not in execin]))
    out.sort(key=lambda a: (a.groundable, a.n, a.jurisdiction == "US"), reverse=True)
    return out


def data_gaps(blocked: dict) -> list[dict]:
    """Data-sourcing targets: a (generic) model blocked in a currency because a role it NEEDS has no
    series there. Grouped by (currency, role) → the models it would unlock. This is the owner's 'data
    shortcoming as a signal', straight from the graph."""
    by: dict = {}
    for (mid, jid), roles in blocked.items():
        for role in roles:
            by.setdefault((jid, role), set()).add(mid)
    return sorted(({"jurisdiction": jid, "role": role, "unlocks": sorted(models)}
                   for (jid, role), models in by.items()),
                  key=lambda g: (g["jurisdiction"], g["role"]))


def port_backlog(generic: dict, execin: set, jur_ids: list[str]) -> list[str]:
    """Porting targets: US-welded models (generic=False) that run in US only — they must be rewritten to
    role-based inputs before they can reach any other currency. The non-data half of the backlog."""
    non_us = [j for j in jur_ids if j != "US"]
    out = []
    for mid, is_generic in generic.items():
        if not is_generic and not any((mid, j) in execin for j in non_us):
            out.append(mid)
    return sorted(out)


def load_facts(driver, catalog: str = "horizon3") -> dict:
    """Pull the plain facts the pure functions need from the live spine."""
    with driver.session() as s:
        def data(cy):
            return s.run(cy, cat=catalog).data()
        uses: dict = {}
        for r in data("MATCH (dm:DecisionMaker {catalog:$cat})-[:USES]->(m:Model) "
                      "RETURN dm.id AS dm, collect(m.id) AS models"):
            uses[r["dm"]] = r["models"]
        decisions = {r["dm"]: r["text"] for r in data(
            "MATCH (dm:DecisionMaker {catalog:$cat})-[:MAKES]->(d:Decision) RETURN dm.id AS dm, d.text AS text")}
        execin = {(r["m"], r["j"]) for r in data(
            "MATCH (m:Model {catalog:$cat})-[:EXECUTABLE_IN]->(j:Jurisdiction) RETURN m.id AS m, j.id AS j")}
        generic = {r["m"]: bool(r["g"]) for r in data(
            "MATCH (m:Model {catalog:$cat, source:'catalog/graph'}) RETURN m.id AS m, m.generic AS g")}
        jur_ids = [r["j"] for r in data(
            "MATCH (j:Jurisdiction {catalog:$cat}) RETURN j.id AS j ORDER BY j")]
        blocked: dict = {}
        for r in data("MATCH (m:Model {catalog:$cat})-[:NEEDS]->(r:Role)-[:MISSING_IN]->(j:Jurisdiction) "
                      "RETURN m.id AS m, j.id AS j, collect(r.name) AS roles"):
            blocked[(r["m"], r["j"])] = r["roles"]
    return {"uses": uses, "decisions": decisions, "execin": execin, "generic": generic,
            "jur_ids": jur_ids, "blocked": blocked}


def _driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7688"),
                                auth=(os.getenv("NEO4J_USERNAME", "neo4j"),
                                      os.getenv("NEO4J_PASSWORD", "devpassword")))


def main() -> None:
    d = _driver()
    try:
        f = load_facts(d)
    finally:
        d.close()
    analyses = enumerate_analyses(f["uses"], f["execin"], f["jur_ids"], f["decisions"])
    groundable = [a for a in analyses if a.groundable]
    print(f"THE ARTICLE SET — {len(groundable)} groundable (decision-maker × currency) analyses "
          f"(of {len(analyses)} possible), from the graph, no persona list:\n")
    for a in groundable:
        print(f"  {a.jurisdiction:3} {a.decision_maker:26} {a.n}/{a.total_models} models  «{a.decision[:44]}»")
    near = [a for a in analyses if not a.groundable and a.n]
    if near:
        print(f"\nNEAR-MISSES ({len(near)} — some models ground, below the {3}-model floor):")
        for a in sorted(near, key=lambda x: -x.n)[:12]:
            print(f"  {a.jurisdiction:3} {a.decision_maker:26} {a.n}/{a.total_models}  "
                  f"has: {', '.join(a.grounded_models)}")
    gaps = data_gaps(f["blocked"])
    if gaps:
        print(f"\nDATA-SOURCING TARGETS ({len(gaps)} role×currency gaps — get these to unlock models):")
        for g in gaps[:15]:
            print(f"  {g['jurisdiction']:3} need '{g['role']}' → unlocks {', '.join(g['unlocks'])}")
    port = port_backlog(f["generic"], f["execin"], f["jur_ids"])
    print(f"\nPORTING BACKLOG ({len(port)} US-welded models — rewrite to roles to leave the US):\n  "
          + ", ".join(port))


if __name__ == "__main__":
    main()
