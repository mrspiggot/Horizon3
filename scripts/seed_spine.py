"""Seed the model spine with what is TRUE — a graph that proves executability instead of asserting it,
NOW ACROSS CURRENCIES, so the graph can steer which analyses are grounded in which jurisdiction.

WHAT THIS DOES
--------------
`executable` is not read off a YAML field. Every candidate is EXECUTED here, now, and per JURISDICTION,
and the graph carries the evidence:

    (:Model)-[:EXECUTABLE_IN {points:281, as_of:'2026-05', run_id:'…'}]->(:Jurisdiction {id:'US'})
    (:Model)-[:EXECUTABLE_IN {points:216, as_of:'2026-05'}]->(:Jurisdiction {id:'EU'})   ← ran on euro data

A US-welded model (concrete series_id, no roles) is US-only by construction — attempted only in US. A
jurisdiction-generic model (inputs carry `role:`) is attempted in every jurisdiction; the role→series
resolver decides — a missing binding is NOT a crash but the recorded gap (:Role)-[:MISSING_IN]->(:J),
which is the owner's "report loudly where we need more data" applied per currency.

The currency + data-binding structure (Jurisdiction, DataSeries, BOUND_TO, MISSING_IN) recovers what the
now-orphaned seed_graph.py / seed_neo4j_spine.py encoded and the narrow live spine had dropped.

`m.executable` (the single US boolean the existing selector reads) is kept for backward-compat = the US
cell of the matrix; the per-currency truth is the EXECUTABLE_IN relationships.

    ~/venv/bin/python scripts/seed_spine.py            # prove per (model,currency) + seed
    ~/venv/bin/python scripts/seed_spine.py --dry-run  # prove only, no writes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402
import yaml      # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.graph_corpus import run_model  # noqa: E402
from render.model_store import record_run  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GRAPH_DIR = REPO / "catalog" / "graph"          # the executable catalog — what writes articles
MODELS_DIR = REPO / "catalog" / "models"        # the design catalog — specs, no execution path
JURIS_FILE = REPO / "catalog" / "jurisdictions.yaml"
CATALOG = "horizon3"


def _load(dir_: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(dir_.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        if isinstance(d, dict) and d.get("model_id"):
            out[d["model_id"]] = d
    return out


def _load_jurisdictions() -> tuple[dict, list]:
    j = yaml.safe_load(JURIS_FILE.read_text())
    return j.get("roles") or {}, j.get("jurisdictions") or []


def _is_generic(doc: dict) -> bool:
    """A model is jurisdiction-generic iff it declares instances OR any input carries a semantic role.
    Otherwise its inputs name concrete US series and it is US-only by construction."""
    return bool(doc.get("instances")) or any(i.get("role") for i in (doc.get("inputs") or []))


def prove_matrix(conn, graph_docs: dict, jur_ids: list[str]) -> dict[str, dict]:
    """Per (model, jurisdiction) executability, PROVEN by running. Returns {mid: {jur: cell}} where a
    cell is {executable, points, as_of, run_id} or {executable:False, why}. A generic model is attempted
    in every jurisdiction; a missing role-binding raises KeyError in the resolver and is recorded as the
    gap, not a failure of the model."""
    matrix: dict[str, dict] = {}
    for mid, doc in graph_docs.items():
        candidates = jur_ids if _is_generic(doc) else ["US"]
        cells: dict[str, dict] = {}
        for jid in candidates:
            try:
                run = run_model(mid, conn, instance=jid)
                hist = run.get("history") or []
                if not hist:
                    cells[jid] = {"executable": False, "why": "ran, no observations"}
                    continue
                rid = record_run(conn, run, instance=jid)
                cells[jid] = {"executable": True, "points": len(hist),
                              "as_of": str(hist[-1].as_of)[:10], "run_id": rid}
            except KeyError as exc:                       # missing role binding = the data gap, not a bug
                cells[jid] = {"executable": False, "why": f"unbound: {str(exc).strip(chr(39))[:110]}"}
            except Exception as exc:
                cells[jid] = {"executable": False, "why": f"{type(exc).__name__}: {str(exc)[:80]}"}
        matrix[mid] = cells
        ok = [j for j, c in cells.items() if c["executable"]]
        tag = "generic" if _is_generic(doc) else "US-welded"
        print(f"  {mid:32} [{tag:9}] executable in: {', '.join(ok) or 'NONE'}", file=sys.stderr)
    return matrix


def _why_not(doc: dict) -> str:
    missing = [k for k in ("history", "charts") if k not in doc]
    if not (doc.get("execution") or {}).get("implemented_by") and not doc.get("implemented_by"):
        missing.append("implemented_by")
    return ("design-stage spec — missing " + ", ".join(missing)) if missing else "not in catalog/graph"


from render.jurisdiction_facts import brand_terms as _brand_terms  # noqa: E402  (canonical, shared with runtime)


def seed_jurisdictions(s, roles: dict, jurisdictions: list) -> None:
    """Jurisdiction + DataSeries + role→series binding per jurisdiction; a null/absent binding is a
    recorded MISSING_IN gap. vocab/calibration ride as JSON props (Neo4j has no nested maps); brand_terms
    is denormalised for the neutrality query. This is the currency+data layer the vision needs."""
    for rname, rmeta in roles.items():
        s.run("MERGE (r:Role {name:$r, catalog:$cat}) SET r.kind=$k, r.desc=$d",
              cat=CATALOG, r=rname, k=(rmeta or {}).get("kind", ""), d=((rmeta or {}).get("desc", "") or "")[:220])
    for j in jurisdictions:
        vocab, calib = j.get("vocab") or {}, j.get("calibration") or {}
        s.run("""MERGE (jn:Jurisdiction {id:$id, catalog:$cat})
                 SET jn.central_bank=$cb, jn.ccy=$ccy, jn.scope=$scope, jn.display_order=$ord,
                     jn.vocab=$vocab, jn.calibration=$calib, jn.brand_terms=$terms""",
              cat=CATALOG, id=j["id"], cb=j.get("central_bank", ""), ccy=j.get("ccy", ""),
              scope=j.get("scope", ""), ord=j.get("display_order", 999),
              vocab=json.dumps(vocab), calib=json.dumps(calib), terms=_brand_terms(vocab))
        binds = j.get("bindings") or {}
        for rname in roles:                               # iterate the whole vocabulary → absent == missing
            b = binds.get(rname)
            if b and b.get("ref"):
                s.run("""MATCH (r:Role {name:$r, catalog:$cat}), (jn:Jurisdiction {id:$jid, catalog:$cat})
                         MERGE (d:DataSeries {ref:$ref, catalog:$cat}) SET d.source=$src
                         MERGE (r)-[bt:BOUND_TO {jurisdiction:$jid}]->(d) SET bt.source=$src
                         MERGE (jn)-[:HAS_SERIES]->(d)""",
                      cat=CATALOG, r=rname, jid=j["id"], ref=b["ref"], src=b.get("source", ""))
            else:
                s.run("""MATCH (r:Role {name:$r, catalog:$cat}), (jn:Jurisdiction {id:$jid, catalog:$cat})
                         MERGE (r)-[:MISSING_IN]->(jn)""", cat=CATALOG, r=rname, jid=j["id"])


def seed(driver, graph_docs, design_docs, matrix, personas, roles, jurisdictions) -> None:
    with driver.session() as s:
        s.run("MATCH (n {catalog:$cat}) DETACH DELETE n", cat=CATALOG)
        seed_jurisdictions(s, roles, jurisdictions)

        for mid, d in graph_docs.items():
            cells = matrix.get(mid, {})
            us = cells.get("US", {"executable": False, "why": "never attempted"})
            s.run(
                """MERGE (m:Model {id:$id, catalog:$cat})
                   SET m.name=$name, m.family=$family, m.source='catalog/graph', m.generic=$gen,
                       m.executable=$ex, m.points=$pts, m.as_of=$as_of, m.run_id=$rid,
                       m.why_not=$why, m.method=$method""",
                cat=CATALOG, id=mid, name=d.get("name", mid), family=d.get("family", "?"),
                gen=_is_generic(d), ex=us["executable"], pts=us.get("points"), as_of=us.get("as_of"),
                rid=us.get("run_id"), why=us.get("why"),
                method=d.get("method_note") or d.get("method", ""))

            # the currency truth: one EXECUTABLE_IN per jurisdiction the model actually ran in
            for jid, c in cells.items():
                if c.get("executable"):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat}), (jn:Jurisdiction {id:$jid, catalog:$cat})
                             MERGE (m)-[e:EXECUTABLE_IN]->(jn)
                             SET e.points=$pts, e.as_of=$as_of, e.run_id=$rid""",
                          cat=CATALOG, id=mid, jid=jid, pts=c.get("points"), as_of=c.get("as_of"),
                          rid=c.get("run_id"))

            for o in d.get("outputs") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                         MERGE (o:Output {name:$n, model:$id, catalog:$cat})
                         SET o.unit=$u, o.meaning=$mean MERGE (m)-[:PRODUCES]->(o)""",
                      cat=CATALOG, id=mid, n=o.get("name"), u=o.get("unit", ""), mean=o.get("meaning", ""))

            # model → required data: a generic model NEEDS a semantic Role; a welded one NEEDS_SERIES a
            # concrete DataSeries. This is what lets the enumerator compute per-currency groundedness.
            for i in d.get("inputs") or []:
                if i.get("role"):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                             MERGE (r:Role {name:$r, catalog:$cat}) MERGE (m)-[:NEEDS]->(r)""",
                          cat=CATALOG, id=mid, r=i["role"])
                elif i.get("series_id"):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                             MERGE (ds:DataSeries {ref:$sid, catalog:$cat}) SET ds.source=$src
                             MERGE (m)-[:NEEDS_SERIES]->(ds)""",
                          cat=CATALOG, id=mid, sid=i["series_id"], src=i.get("db_source", ""))

            for ch in d.get("charts") or []:
                if cid := ch.get("id"):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                             MERGE (v:Visualization {id:$c, catalog:$cat})
                             SET v.chart_type=$t, v.insight=$ins, v.role=$role
                             MERGE (m)-[:RENDERS]->(v)""",
                          cat=CATALOG, id=mid, c=cid, t=ch.get("chart_type", ""),
                          ins=ch.get("insight", ""), role=ch.get("role", ""))

        for mid, d in design_docs.items():
            if mid in graph_docs:
                continue
            s.run("""MERGE (m:Model {id:$id, catalog:$cat})
                     SET m.name=$name, m.family=$family, m.source='catalog/models',
                         m.executable=false, m.why_not=$why, m.umd_impl=$impl""",
                  cat=CATALOG, id=mid, name=d.get("name", mid), family=d.get("family", "?"),
                  why=_why_not(d), impl=d.get("implemented_by"))

        for pid, p in personas.items():
            s.run("""MERGE (dm:DecisionMaker {id:$pid, catalog:$cat}) SET dm.name=$name
                     MERGE (dec:Decision {id:$pid, catalog:$cat}) SET dec.text=$decision
                     MERGE (dm)-[:MAKES]->(dec)
                     WITH dm, dec
                     UNWIND $uses AS mid
                       MATCH (m:Model {id:mid, catalog:$cat})
                       MERGE (dm)-[:USES]->(m) MERGE (m)-[:INFORMS]->(dec)""",
                  cat=CATALOG, pid=pid, name=p.get("name", pid),
                  decision=p.get("decision", ""), uses=p.get("models") or [])


def report(driver) -> int:
    """The conviction test, now per currency: how wide is the grounded (model × jurisdiction) matrix?"""
    with driver.session() as s:
        tot = s.run("MATCH (m:Model {catalog:$cat, source:'catalog/graph'}) RETURN count(m) AS n",
                    cat=CATALOG).single()["n"]
        cells = s.run("MATCH (:Model {catalog:$cat})-[:EXECUTABLE_IN]->(:Jurisdiction) RETURN count(*) AS n",
                      cat=CATALOG).single()["n"]
        print(f"\nSPINE: {tot} executable-catalog models — {cells} proven (model × currency) cells")

        rows = s.run("""MATCH (jn:Jurisdiction {catalog:$cat})
                        OPTIONAL MATCH (m:Model)-[:EXECUTABLE_IN]->(jn)
                        RETURN jn.id AS jid, jn.ccy AS ccy, count(m) AS n ORDER BY n DESC""",
                     cat=CATALOG).data()
        print("\nGROUNDED MODELS PER CURRENCY (proven by a real run):")
        for r in rows:
            print(f"  {r['jid']:3} {r['ccy']:4} {r['n']:3} models")

        multi = s.run("""MATCH (m:Model {catalog:$cat})-[:EXECUTABLE_IN]->(jn:Jurisdiction)
                         WITH m, collect(jn.id) AS js WHERE size(js) > 1
                         RETURN m.id AS id, js ORDER BY id""", cat=CATALOG).data()
        print(f"\nMULTI-CURRENCY MODELS ({len(multi)} run in more than one jurisdiction):")
        for r in multi:
            print(f"  {r['id']:32} {', '.join(sorted(r['js']))}")

        # data-gap signal: a generic model needs a role that is MISSING in some jurisdiction
        gaps = s.run("""MATCH (m:Model {catalog:$cat})-[:NEEDS]->(r:Role)-[:MISSING_IN]->(jn:Jurisdiction)
                        RETURN jn.id AS jid, r.name AS role, collect(DISTINCT m.id) AS models
                        ORDER BY jid, role""", cat=CATALOG).data()
        if gaps:
            print(f"\nDATA GAPS (a generic model blocked in a currency by a missing series — sourcing targets):")
            for g in gaps[:20]:
                print(f"  {g['jid']:3} missing '{g['role']}' → blocks {', '.join(g['models'][:4])}")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="prove executability, write nothing")
    args = ap.parse_args()

    graph_docs, design_docs = _load(GRAPH_DIR), _load(MODELS_DIR)
    roles, jurisdictions = _load_jurisdictions()
    jur_ids = [j["id"] for j in jurisdictions]
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]
    print(f"catalog/graph: {len(graph_docs)} models   jurisdictions: {', '.join(jur_ids)}")
    print(f"\nPROVING EXECUTABILITY per (model × currency) — running candidates", file=sys.stderr)

    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    matrix = prove_matrix(conn, graph_docs, jur_ids)
    cells = sum(1 for c in matrix.values() for x in c.values() if x["executable"])
    print(f"\n{cells} proven (model × currency) cells across {len(graph_docs)} models")
    if args.dry_run:
        for mid, c in sorted(matrix.items()):
            ok = [j for j, x in c.items() if x["executable"]]
            print(f"  {mid:32} {', '.join(ok) or 'NONE'}")
        return

    driver = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7688"),
                                  auth=(os.getenv("NEO4J_USERNAME", "neo4j"),
                                        os.getenv("NEO4J_PASSWORD", "devpassword")))
    seed(driver, graph_docs, design_docs, matrix, personas, roles, jurisdictions)
    rc = report(driver)
    driver.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
