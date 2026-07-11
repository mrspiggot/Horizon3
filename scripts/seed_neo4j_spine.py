#!/usr/bin/env python
"""Seed the Horizon3 model spine into horizon-neo4j, then run the conviction test (§09 D4 + D6).

The catalog (catalog/models/*.yaml + personas.yaml) is authored in Horizon3 and LOADED here into
UMD's Neo4j (horizon-neo4j, Bolt :7688) as the graph shape §06 prescribes:

    (DecisionMaker)-[:MAKES]->(Decision)
    (DecisionMaker)-[:USES]->(Model)-[:INFORMS]->(Decision)
    (Model)-[:GENERIC_OVER]->(Axis)-[has]->(Instance)   (Model)-[:INSTANTIATES]->(Instance)
    (Model)-[:HAS_INPUT]->(Role)   (Model)-[:RENDERS]->(Visualization)
    (Model)-[:EXECUTED_BY]->(Implementation)             (impl models only)

Every spine node carries {catalog:'horizon3'} so we can idempotently clear+reseed OUR subgraph
without touching the 2767-node Horizon2-era substrate already in the database.

The CONVICTION TEST (§09 D6 embryo) then traces, for EVERY persona:
    decision -> model -> inputs present -> execution (impl) or honest stub -> instances -> renders
and reports per-persona PASS + a clean spot-trace of 3 personas.

Usage:
  ~/venv/bin/python scripts/seed_neo4j_spine.py            # seed + verify
  ~/venv/bin/python scripts/seed_neo4j_spine.py --verify   # verify only (no writes)

Env: NEO4J_URI (default bolt://localhost:7688), NEO4J_USERNAME (neo4j), NEO4J_PASSWORD (devpassword).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from neo4j import GraphDatabase

REPO = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO / "catalog" / "models"
PERSONAS_FILE = REPO / "catalog" / "personas.yaml"

CATALOG = "horizon3"
AXIS_KEYWORDS = ["currency", "underlying", "event", "commodity", "pair", "issuer", "equity"]

_TTY = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
OK, FAIL = c("32", "PASS"), c("31", "FAIL")
TICK, CROSS = c("32", "✓"), c("31", "✗")


def _axis_of(doc: dict) -> str:
    go = doc.get("generic_over") or []
    for kw in AXIS_KEYWORDS:
        if kw in go:
            return kw
    return "currency"


def load_catalog() -> tuple[dict, list]:
    docs = {f.stem: yaml.safe_load(f.read_text()) for f in sorted(MODELS_DIR.glob("*.yaml"))}
    personas = yaml.safe_load(PERSONAS_FILE.read_text()).get("personas", [])
    return docs, personas


def _model_rows(docs: dict) -> list[dict]:
    rows = []
    for stem, d in docs.items():
        mid = d.get("model_id", stem)
        is_stub = d.get("build_stub") is True
        is_direct = d.get("data_direct") is True
        kind = "stub" if is_stub else ("data_direct" if is_direct else "impl")
        claimed = d.get("instances") or d.get("jurisdictions") or []
        roles = sorted({i.get("role") for i in (d.get("inputs") or []) if i.get("role")})
        viz = [(v.get("id"), v.get("chart_type") or "") for v in (d.get("visualizations") or [])]
        rows.append({
            "id": mid, "name": d.get("name", mid), "family": d.get("family", "?"),
            "kind": kind, "axis": _axis_of(d), "instances": list(claimed),
            "roles": roles, "viz": viz,
            "impl": d.get("implemented_by") if kind == "impl" else None,
        })
    return rows


def seed(driver, docs: dict, personas: list) -> None:
    models = _model_rows(docs)
    with driver.session() as s:
        # idempotent: clear only OUR spine
        s.run(f"MATCH (n {{catalog:$cat}}) DETACH DELETE n", cat=CATALOG)

        # Separate statements per collection — an empty UNWIND ($instances=[] for stubs) must NOT
        # zero out the row pipeline and drop the roles/viz that follow it.
        for m in models:
            s.run(
                """MERGE (mo:Model {id:$id, catalog:$cat})
                   SET mo.name=$name, mo.family=$family, mo.kind=$kind
                   MERGE (ax:Axis {name:$axis, catalog:$cat})
                   MERGE (mo)-[:GENERIC_OVER]->(ax)""",
                cat=CATALOG, id=m["id"], name=m["name"], family=m["family"],
                kind=m["kind"], axis=m["axis"])
            if m["instances"]:
                s.run(
                    """MATCH (mo:Model {id:$id, catalog:$cat})
                       MATCH (ax:Axis {name:$axis, catalog:$cat})
                       UNWIND $instances AS inst
                         MERGE (i:Instance {id:inst, axis:$axis, catalog:$cat})
                         MERGE (ax)-[:HAS_INSTANCE]->(i)
                         MERGE (mo)-[:INSTANTIATES]->(i)""",
                    cat=CATALOG, id=m["id"], axis=m["axis"], instances=m["instances"])
            if m["roles"]:
                s.run(
                    """MATCH (mo:Model {id:$id, catalog:$cat})
                       UNWIND $roles AS rn
                         MERGE (r:Role {name:rn, catalog:$cat})
                         MERGE (mo)-[:HAS_INPUT]->(r)""",
                    cat=CATALOG, id=m["id"], roles=m["roles"])
            if m["viz"]:
                s.run(
                    """MATCH (mo:Model {id:$id, catalog:$cat})
                       UNWIND $viz AS v
                         MERGE (vz:Visualization {id:v[0], catalog:$cat})
                         SET vz.chart_type=v[1]
                         MERGE (mo)-[:RENDERS]->(vz)""",
                    cat=CATALOG, id=m["id"], viz=m["viz"])
            if m["impl"]:
                s.run(
                    """MATCH (mo:Model {id:$id, catalog:$cat})
                       MERGE (im:Implementation {ref:$impl, catalog:$cat})
                       MERGE (mo)-[:EXECUTED_BY]->(im)""",
                    cat=CATALOG, id=m["id"], impl=m["impl"])

        for p in personas:
            s.run(
                """
                MERGE (dm:DecisionMaker {id:$pid, catalog:$cat}) SET dm.name=$name
                MERGE (dec:Decision {id:$pid, catalog:$cat}) SET dec.text=$decision
                MERGE (dm)-[:MAKES]->(dec)
                WITH dm, dec
                UNWIND $uses AS muid
                  MATCH (mo:Model {id:muid, catalog:$cat})
                  MERGE (dm)-[:USES]->(mo)
                  MERGE (mo)-[:INFORMS]->(dec)
                """,
                cat=CATALOG, pid=p["persona_id"], name=p.get("name", p["persona_id"]),
                decision=p.get("decision", ""), uses=p.get("uses", []) or [])


def counts(driver) -> None:
    with driver.session() as s:
        print("\nSPINE NODE COUNTS")
        for lbl in ("DecisionMaker", "Decision", "Model", "Axis", "Instance", "Role",
                    "Visualization", "Implementation"):
            n = s.run(f"MATCH (n:{lbl} {{catalog:$cat}}) RETURN count(n) AS c", cat=CATALOG).single()["c"]
            print(f"  :{lbl:16} {n}")
        print("SPINE EDGE COUNTS")
        for rel in ("MAKES", "USES", "INFORMS", "GENERIC_OVER", "HAS_INSTANCE",
                    "INSTANTIATES", "HAS_INPUT", "RENDERS", "EXECUTED_BY"):
            n = s.run(f"MATCH (a {{catalog:$cat}})-[r:{rel}]->() RETURN count(r) AS c",
                      cat=CATALOG).single()["c"]
            print(f"  -[:{rel:14}]-> {n}")


def conviction_test(driver) -> int:
    """For every persona: decision -> model(s) -> inputs -> execution/stub -> instances -> renders."""
    print("\nCONVICTION TEST  (every persona traces decision → model → inputs → execution → outputs)")
    failures = 0
    with driver.session() as s:
        rows = s.run(
            """
            MATCH (dm:DecisionMaker {catalog:$cat})-[:MAKES]->(dec:Decision)
            OPTIONAL MATCH (dm)-[:USES]->(mo:Model)
            WITH dm, dec, collect(mo) AS models
            RETURN dm.id AS pid, dm.name AS name, dec.text AS decision,
                   size(models) AS n_models,
                   [m IN models WHERE NOT (m)-[:HAS_INPUT]->() | m.id] AS models_without_inputs,
                   [m IN models WHERE m.kind='impl' AND NOT (m)-[:EXECUTED_BY]->() | m.id] AS impl_without_exec,
                   [m IN models WHERE NOT (m)-[:RENDERS]->() | m.id] AS models_without_viz,
                   [m IN models WHERE m.kind='impl' | m.id] AS impl_models
            ORDER BY pid
            """, cat=CATALOG).data()

        for r in rows:
            errs = []
            if r["n_models"] == 0:
                errs.append("uses 0 models")
            if r["models_without_inputs"]:
                errs.append(f"no inputs: {r['models_without_inputs']}")
            if r["impl_without_exec"]:
                errs.append(f"impl w/o execution: {r['impl_without_exec']}")
            if r["models_without_viz"]:
                errs.append(f"no viz: {r['models_without_viz']}")
            status = OK if not errs else FAIL
            failures += bool(errs)
            print(f"  {status}  {r['pid']:26} {r['n_models']} models "
                  f"({len(r['impl_models'])} impl)" + ("" if not errs else "  " + "; ".join(errs)))

    # spot-trace 3 personas end to end
    print("\nSPOT-TRACE (3 personas: decision → model → role/instance/execution)")
    for pid in ("macro_rates_trader", "fx_trader", "equity_multiasset_pm"):
        with driver.session() as s:
            t = s.run(
                """
                MATCH (dm:DecisionMaker {id:$pid, catalog:$cat})-[:MAKES]->(dec:Decision)
                MATCH (dm)-[:USES]->(mo:Model)-[:EXECUTED_BY]->(im:Implementation)
                WITH dm, dec, mo, im LIMIT 1
                OPTIONAL MATCH (mo)-[:HAS_INPUT]->(r:Role)
                OPTIONAL MATCH (mo)-[:INSTANTIATES]->(i:Instance)
                OPTIONAL MATCH (mo)-[:GENERIC_OVER]->(ax:Axis)
                RETURN dm.name AS who, dec.text AS decision, mo.id AS model, ax.name AS axis,
                       im.ref AS exec, collect(DISTINCT r.name) AS roles,
                       count(DISTINCT i) AS n_inst
                """, cat=CATALOG, pid=pid).single()
            if t:
                print(f"  {TICK} {t['who']}: \"{t['decision']}\"")
                print(f"      → model {t['model']}  (generic over {t['axis']}, {t['n_inst']} instances)")
                print(f"      → inputs {t['roles']}")
                print(f"      → executed by {t['exec']}")
            else:
                print(f"  {CROSS} {pid}: no impl-backed trace")
                failures += 1

    print(f"\nCONVICTION: {'ALL PERSONAS PASS' if not failures else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


def main() -> int:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "devpassword")
    verify_only = "--verify" in sys.argv

    docs, personas = load_catalog()
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
        print(f"horizon-neo4j: {uri}  (catalog='{CATALOG}' subgraph)")
        if not verify_only:
            seed(driver, docs, personas)
            print(f"seeded {len(docs)} models + {len(personas)} personas")
        counts(driver)
        return conviction_test(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
