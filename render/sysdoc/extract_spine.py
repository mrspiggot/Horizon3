"""Neo4j spine census — the fastest-churning part of the system, read from ground truth.

Reuses the connection pattern and census Cypher from scripts/seed_spine.py and
render/selector/nodes.py. APOC is NOT installed here, so this uses only plain Cypher
(db.labels / db.relationshipTypes + MATCH counts). Everything is namespaced by
`catalog:'horizon3'`.

Degrades gracefully: if bolt:7688 is unreachable the census returns
`SpineInfo(online=False, error=...)` so the doc still builds (never crash on a doc run).
"""
from __future__ import annotations

import os

from .manifest import SpineInfo

CATALOG = "horizon3"


def _driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7688"),
        auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "devpassword")),
    )


def extract_spine() -> SpineInfo:
    try:
        d = _driver()
    except Exception as exc:  # driver import / construction failed
        return SpineInfo(online=False, error=f"{type(exc).__name__}: {exc}")
    try:
        with d.session() as s:
            def one(q, **kw):
                rec = s.run(q, **kw).single()
                return rec[0] if rec else None

            # Scope labels/relationships to OUR catalog subgraph — horizon-neo4j is shared
            # with Horizon2/UMD, so db.labels()/db.relationshipTypes() would dump everything.
            # Traverse from :Model {catalog} (indexed) one hop out.
            rec = s.run("MATCH (m:Model {catalog:$c}) OPTIONAL MATCH (m)-[r]-(x) "
                        "RETURN collect(DISTINCT type(r)) AS rels, "
                        "collect(DISTINCT labels(x)) AS lbls", c=CATALOG).single()
            rels = list(rec["rels"]) if rec else []
            neigh = {lab for sub in ((rec["lbls"] if rec else []) or []) for lab in (sub or [])}
            labels = sorted({"Model", *neigh})
            execu = one("MATCH (m:Model {catalog:$c, source:'catalog/graph'}) RETURN count(m)", c=CATALOG) or 0
            cells = one("MATCH (:Model {catalog:$c})-[:EXECUTABLE_IN]->(:Jurisdiction) "
                        "RETURN count(*)", c=CATALOG) or 0
            by_family = [{"family": r["family"], "count": r["count"]} for r in s.run(
                "MATCH (m:Model {catalog:$c, source:'catalog/graph'}) "
                "RETURN coalesce(m.family,'(none)') AS family, count(*) AS count "
                "ORDER BY count DESC, family", c=CATALOG)]
            by_juris = [{"id": r["id"], "ccy": r["ccy"], "models": r["models"]} for r in s.run(
                "MATCH (jn:Jurisdiction {catalog:$c}) "
                "OPTIONAL MATCH (m:Model)-[:EXECUTABLE_IN]->(jn) "
                "RETURN jn.id AS id, jn.ccy AS ccy, count(m) AS models "
                "ORDER BY models DESC, id", c=CATALOG)]
            gaps = [{"jurisdiction": r["jurisdiction"], "role": r["role"], "models": r["models"]}
                    for r in s.run(
                "MATCH (m:Model {catalog:$c})-[:NEEDS]->(r:Role)-[:MISSING_IN]->(jn:Jurisdiction) "
                "RETURN jn.id AS jurisdiction, r.name AS role, collect(DISTINCT m.id) AS models "
                "ORDER BY jurisdiction, role", c=CATALOG)]
        return SpineInfo(
            online=True, executable_models=int(execu), proven_cells=int(cells),
            labels=sorted(labels), rel_types=sorted(rels),
            by_family=by_family, by_jurisdiction=by_juris, gaps=gaps,
        )
    except Exception as exc:
        return SpineInfo(online=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            d.close()
        except Exception:
            pass
