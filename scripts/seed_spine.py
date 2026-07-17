"""Seed the model spine with what is TRUE — a graph that proves executability instead of asserting it.

WHY THIS REPLACES seed_neo4j_spine.py's CLAIM
---------------------------------------------
The old spine seeds `catalog/models` (38 design specs) and reports "CONVICTION: ALL PERSONAS PASS".
Its test checks that each model HAS `inputs`, HAS `visualizations`, HAS an `implemented_by` string —
that the YAML has fields. It never asks whether the model runs. It cannot: those 38 hold a prose
`spec` ("Principal-component decomposition of the curve…"), and none of them has `history`,
`db_sources` or `charts`. `render.graph_corpus.run_model('curve_pca')` raises FileNotFoundError,
because the article engine reads `catalog/graph` and they are not there.

Meanwhile the 28 models in `catalog/graph` — the ones that executed 8 articles on 2026-07-17 — are
INVISIBLE to the graph. The overlap between the two catalogs is 3.

So §09's gate ("the Neo4j model spine seeded; every persona traces cleanly decision → model → inputs
→ execution → outputs") passes green over a library that has never produced an artifact, while the
library that produces everything is absent. That is the Horizon2 disease the charter names: a
validation box that lies. Selecting models from that graph — which is what §06 role 2 is FOR — would
select models the engine cannot even locate.

WHAT THIS DOES INSTEAD
----------------------
`executable` is not read off a YAML field. Every candidate is EXECUTED here, now, and the node
carries the evidence:

    (:Model {executable:true,  points:281, as_of:'2026-05-28', run_id:'…'})   ← ran, proof recorded
    (:Model {executable:false, why:'no history block — design-stage spec'})    ← honest backlog

The design catalog is still seeded, because knowing what we WANT and cannot yet do is worth having in
the graph — it is the owner's "REPORT LOUDLY where we need to find more" applied to models rather than
data. It is simply never labelled executable.

A model that fails to run is recorded as a failure, not skipped. Silence is how the old spine passed.

    ~/venv/bin/python scripts/seed_spine.py            # prove + seed
    ~/venv/bin/python scripts/seed_spine.py --dry-run  # prove only, no writes
"""
from __future__ import annotations

import argparse
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
CATALOG = "horizon3"


def _load(dir_: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(dir_.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        if isinstance(d, dict) and d.get("model_id"):
            out[d["model_id"]] = d
    return out


def prove(conn, executable_ids: list[str], instance: str = "US") -> dict[str, dict]:
    """Run every candidate. The graph records what happened, never what was hoped for."""
    proof: dict[str, dict] = {}
    for mid in executable_ids:
        try:
            run = run_model(mid, conn, instance=instance)
            hist = run.get("history") or []
            if not hist:
                proof[mid] = {"executable": False, "why": "ran but produced no observations"}
                print(f"  EMPTY  {mid:30} ran, delivered nothing", file=sys.stderr)
                continue
            rid = record_run(conn, run, instance=instance)
            proof[mid] = {"executable": True, "points": len(hist),
                          "as_of": str(hist[-1].as_of)[:10], "run_id": rid,
                          "outputs": [o.get("name") for o in (run.get("meta", {}).get("outputs") or [])]}
            print(f"  ok     {mid:30} {len(hist):4} points → {str(hist[-1].as_of)[:10]}")
        except Exception as exc:
            # A model that will not run is a FINDING. The old spine's silence here is exactly how 35
            # unexecutable models came to be certified.
            proof[mid] = {"executable": False, "why": f"{type(exc).__name__}: {str(exc)[:80]}"}
            print(f"  FAIL   {mid:30} {type(exc).__name__}: {str(exc)[:60]}", file=sys.stderr)
    return proof


def _why_not(doc: dict) -> str:
    """Why a design-catalog model cannot execute — stated concretely, not as a shrug."""
    missing = [k for k in ("history", "charts") if k not in doc]
    if not (doc.get("execution") or {}).get("implemented_by") and not doc.get("implemented_by"):
        missing.append("implemented_by")
    return ("design-stage spec — missing " + ", ".join(missing)) if missing else "not in catalog/graph"


def seed(driver, graph_docs: dict, design_docs: dict, proof: dict, personas: dict) -> None:
    with driver.session() as s:
        s.run("MATCH (n {catalog:$cat}) DETACH DELETE n", cat=CATALOG)

        for mid, d in graph_docs.items():
            p = proof.get(mid, {"executable": False, "why": "never attempted"})
            s.run(
                """MERGE (m:Model {id:$id, catalog:$cat})
                   SET m.name=$name, m.family=$family, m.source='catalog/graph',
                       m.executable=$ex, m.points=$pts, m.as_of=$as_of, m.run_id=$rid,
                       m.why_not=$why, m.method=$method""",
                cat=CATALOG, id=mid, name=d.get("name", mid), family=d.get("family", "?"),
                ex=p["executable"], pts=p.get("points"), as_of=p.get("as_of"),
                rid=p.get("run_id"), why=p.get("why"), method=d.get("method_note") or d.get("method", ""))
            for o in d.get("outputs") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                         MERGE (o:Output {name:$n, model:$id, catalog:$cat})
                         SET o.unit=$u, o.meaning=$mean
                         MERGE (m)-[:PRODUCES]->(o)""",
                      cat=CATALOG, id=mid, n=o.get("name"), u=o.get("unit", ""),
                      mean=o.get("meaning", ""))
            for i in d.get("inputs") or []:
                if role := (i.get("role") or i.get("name")):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                             MERGE (r:Role {name:$r, catalog:$cat})
                             MERGE (m)-[:HAS_INPUT]->(r)""", cat=CATALOG, id=mid, r=role)
            for ch in d.get("charts") or []:
                if cid := ch.get("id"):
                    s.run("""MATCH (m:Model {id:$id, catalog:$cat})
                             MERGE (v:Visualization {id:$c, catalog:$cat})
                             SET v.chart_type=$t, v.insight=$ins, v.role=$role
                             MERGE (m)-[:RENDERS]->(v)""",
                          cat=CATALOG, id=mid, c=cid, t=ch.get("chart_type", ""),
                          ins=ch.get("insight", ""), role=ch.get("role", ""))

        # The design catalog: what we want and cannot yet do. Seeded, never labelled executable.
        for mid, d in design_docs.items():
            if mid in graph_docs:
                continue
            s.run(
                """MERGE (m:Model {id:$id, catalog:$cat})
                   SET m.name=$name, m.family=$family, m.source='catalog/models',
                       m.executable=false, m.why_not=$why, m.umd_impl=$impl""",
                cat=CATALOG, id=mid, name=d.get("name", mid), family=d.get("family", "?"),
                why=_why_not(d), impl=d.get("implemented_by"))

        for pid, p in personas.items():
            s.run(
                """MERGE (dm:DecisionMaker {id:$pid, catalog:$cat}) SET dm.name=$name
                   MERGE (dec:Decision {id:$pid, catalog:$cat}) SET dec.text=$decision
                   MERGE (dm)-[:MAKES]->(dec)
                   WITH dm, dec
                   UNWIND $uses AS mid
                     MATCH (m:Model {id:mid, catalog:$cat})
                     MERGE (dm)-[:USES]->(m)
                     MERGE (m)-[:INFORMS]->(dec)""",
                cat=CATALOG, pid=pid, name=p.get("name", pid),
                decision=p.get("decision", ""), uses=p.get("models") or [])


def report(driver) -> int:
    """The conviction test, asked honestly: can every persona reach a model that RAN?"""
    with driver.session() as s:
        tot = s.run("MATCH (m:Model {catalog:$cat}) RETURN count(m) AS n", cat=CATALOG).single()["n"]
        ex = s.run("MATCH (m:Model {catalog:$cat, executable:true}) RETURN count(m) AS n",
                   cat=CATALOG).single()["n"]
        print(f"\nSPINE: {tot} models — {ex} PROVEN executable, {tot - ex} design-stage/failed")

        rows = s.run(
            """MATCH (dm:DecisionMaker {catalog:$cat})-[:MAKES]->(dec:Decision)
               OPTIONAL MATCH (dm)-[:USES]->(m:Model)
               WITH dm, dec, collect(m) AS ms
               RETURN dm.id AS pid,
                      size([x IN ms WHERE x.executable]) AS ok,
                      size(ms) AS n,
                      [x IN ms WHERE NOT x.executable | x.id] AS dead
               ORDER BY pid""", cat=CATALOG).data()
        bad = 0
        print("\nPER PERSONA (models that actually ran / models bound)")
        for r in rows:
            flag = "PASS" if r["ok"] else "FAIL"
            bad += 0 if r["ok"] else 1
            note = f"  dead: {', '.join(r['dead'][:3])}" if r["dead"] else ""
            print(f"  {flag}  {r['pid']:26} {r['ok']}/{r['n']}{note}")

        # The whole point of role 2: a persona may reach ANY proven model, not just its hardcoded few.
        reach = s.run(
            """MATCH (m:Model {catalog:$cat, executable:true})
               WHERE NOT (:DecisionMaker {catalog:$cat})-[:USES]->(m)
               RETURN collect(m.id) AS orphans""", cat=CATALOG).single()["orphans"]
        if reach:
            print(f"\n{len(reach)} PROVEN models no persona is bound to — invisible to every article "
                  f"today, and exactly what role 2 exists to reach:\n  {', '.join(sorted(reach))}")
        return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="prove executability, write nothing")
    args = ap.parse_args()

    graph_docs, design_docs = _load(GRAPH_DIR), _load(MODELS_DIR)
    personas = yaml.safe_load((GRAPH_DIR / "personas.yaml").read_text())["personas"]
    print(f"catalog/graph: {len(graph_docs)} models   catalog/models: {len(design_docs)} models   "
          f"overlap: {len(set(graph_docs) & set(design_docs))}")
    print(f"\nPROVING EXECUTABILITY — running all {len(graph_docs)} candidates")

    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    proof = prove(conn, list(graph_docs))
    ran = sum(1 for p in proof.values() if p["executable"])
    print(f"\n{ran}/{len(graph_docs)} models proven executable by running them")
    if args.dry_run:
        for mid, p in sorted(proof.items()):
            if not p["executable"]:
                print(f"  NOT EXECUTABLE  {mid:30} {p['why']}")
        return

    driver = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7688"),
                                  auth=(os.getenv("NEO4J_USERNAME", "neo4j"),
                                        os.getenv("NEO4J_PASSWORD", "devpassword")))
    seed(driver, graph_docs, design_docs, proof, personas)
    bad = report(driver)
    driver.close()
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
