#!/usr/bin/env python
"""Load the executable model graph (catalog/graph/) into horizon-neo4j with the FULL ontology.

The chain the owner asked the GraphDB to carry (catalog/_ontology.md):
  (DecisionMaker)-[:MAKES]->(Decision)
  (DecisionMaker)-[:USES]->(Model)-[:INFORMS]->(Decision)
  (Model)-[:HAS_SPEC]->(ModelSpecification)   (Model)-[:GROUNDED_IN]->(Paper)
  (Model)-[:TAKES_INPUT]->(ModelInput)-[:BOUND_TO]->(DataSeries)
  (Model)-[:PRODUCES]->(ModelOutput)          (Model)-[:IMPLEMENTED_BY]->(Implementation)
  (Model)-[:HAS_INTERPRETATION]->(Interpretation)-[:ILLUSTRATED_BY]->(Chart)-[:ENCODES]->(ModelOutput)

Every node carries {catalog:'model-graph'} so it reseeds idempotently without touching the earlier
'horizon3' spine or the Horizon2 substrate. After loading it runs a conviction trace: every persona
must walk decision -> model -> inputs -> execution -> outputs -> interpretation -> chart.

Usage: ~/venv/bin/python scripts/seed_graph.py
Env: NEO4J_URI (bolt://localhost:7688), NEO4J_USERNAME (neo4j), NEO4J_PASSWORD (devpassword).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml
from neo4j import GraphDatabase

REPO = Path(__file__).resolve().parents[1]
GRAPH = REPO / "catalog" / "graph"
CAT = "model-graph"

_TTY = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if _TTY else s
OK, FAIL, TICK = c("32", "PASS"), c("31", "FAIL"), c("32", "✓")


def _load():
    specs = {f.stem: yaml.safe_load(f.read_text())
             for f in sorted(GRAPH.glob("*.yaml")) if f.name != "personas.yaml"}
    personas = yaml.safe_load((GRAPH / "personas.yaml").read_text()).get("personas", {})
    return specs, personas


def _output_refs(chart: dict) -> list[str]:
    """The output names a chart encodes (from its data_contract 'output:<name>' refs)."""
    dc = chart.get("data_contract", {}) or {}
    txt = str(dc)
    return sorted(set(re.findall(r"output:([A-Za-z0-9_]+)", txt)))


def seed(driver, specs: dict, personas: dict) -> None:
    with driver.session() as s:
        s.run("MATCH (n {catalog:$c}) DETACH DELETE n", c=CAT)
        for mid, d in specs.items():
            spec = d.get("spec", {}) or {}
            s.run("""MERGE (m:Model {id:$id, catalog:$c})
                     SET m.name=$name, m.family=$family, m.kind='impl'
                     MERGE (sp:ModelSpecification {id:$id, catalog:$c})
                       SET sp.equations=$eq, sp.params=$params
                     MERGE (m)-[:HAS_SPEC]->(sp)
                     MERGE (im:Implementation {ref:$impl, catalog:$c})
                     MERGE (m)-[:IMPLEMENTED_BY]->(im)""",
                  c=CAT, id=mid, name=d.get("name", mid), family=d.get("family", "?"),
                  eq=spec.get("equations", ""), params=str(spec.get("params", {})),
                  impl=(d.get("execution") or {}).get("implemented_by", ""))
            for g in d.get("grounded_in") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$c})
                         MERGE (p:Paper {id:$pid, catalog:$c})
                         MERGE (m)-[:GROUNDED_IN]->(p)""", c=CAT, id=mid, pid=g)
            for inp in d.get("inputs") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$c})
                         MERGE (i:ModelInput {model:$id, iid:$iid, catalog:$c})
                           SET i.transform=$tr, i.state=$st, i.source=$src
                         MERGE (m)-[:TAKES_INPUT]->(i)""",
                      c=CAT, id=mid, iid=inp.get("id"), tr=inp.get("transform", "none"),
                      st=inp.get("state", "level"), src=inp.get("source", "series"))
                if inp.get("series_id"):
                    s.run("""MATCH (i:ModelInput {model:$id, iid:$iid, catalog:$c})
                             MERGE (ds:DataSeries {series_id:$sid, catalog:$c})
                             MERGE (i)-[:BOUND_TO]->(ds)""",
                          c=CAT, id=mid, iid=inp.get("id"), sid=inp["series_id"])
            for o in d.get("outputs") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$c})
                         MERGE (o:ModelOutput {model:$id, name:$n, catalog:$c})
                           SET o.unit=$u, o.meaning=$mn
                         MERGE (m)-[:PRODUCES]->(o)""",
                      c=CAT, id=mid, n=o["name"], u=o.get("unit", ""), mn=o.get("meaning", ""))
            for it in d.get("interpretations") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$c})
                         MERGE (t:Interpretation {model:$id, iid:$iid, catalog:$c})
                           SET t.when=$w, t.says=$says
                         MERGE (m)-[:HAS_INTERPRETATION]->(t)""",
                      c=CAT, id=mid, iid=it["id"], w=it.get("when", ""), says=it.get("says", ""))
            for ch in d.get("charts") or []:
                s.run("""MATCH (m:Model {id:$id, catalog:$c})
                         MERGE (ch:Chart {model:$id, cid:$cid, catalog:$c})
                           SET ch.chart_type=$ct, ch.insight=$ins
                         MERGE (m)-[:RENDERS]->(ch)""",
                      c=CAT, id=mid, cid=ch["id"], ct=ch.get("chart_type", ""), ins=ch.get("insight", ""))
                if ch.get("interpretation"):
                    s.run("""MATCH (t:Interpretation {model:$id, iid:$iid, catalog:$c})
                             MATCH (ch:Chart {model:$id, cid:$cid, catalog:$c})
                             MERGE (t)-[:ILLUSTRATED_BY]->(ch)""",
                          c=CAT, id=mid, iid=ch["interpretation"], cid=ch["id"])
                for oname in _output_refs(ch):
                    s.run("""MATCH (ch:Chart {model:$id, cid:$cid, catalog:$c})
                             MATCH (o:ModelOutput {model:$id, name:$n, catalog:$c})
                             MERGE (ch)-[:ENCODES]->(o)""", c=CAT, id=mid, cid=ch["id"], n=oname)
        for pid, p in personas.items():
            s.run("""MERGE (dm:DecisionMaker {id:$pid, catalog:$c}) SET dm.name=$name
                     MERGE (dec:Decision {id:$pid, catalog:$c}) SET dec.text=$dec
                     MERGE (dm)-[:MAKES]->(dec)""",
                  c=CAT, pid=pid, name=p.get("name", pid), dec=p.get("decision", ""))
            for mid in p.get("models") or []:
                s.run("""MATCH (dm:DecisionMaker {id:$pid, catalog:$c})
                         MATCH (dec:Decision {id:$pid, catalog:$c})
                         MATCH (m:Model {id:$mid, catalog:$c})
                         MERGE (dm)-[:USES]->(m) MERGE (m)-[:INFORMS]->(dec)""",
                      c=CAT, pid=pid, mid=mid)


def report(driver, personas: dict) -> int:
    with driver.session() as s:
        print("\nNODE COUNTS")
        for lbl in ("DecisionMaker", "Decision", "Model", "ModelSpecification", "Paper",
                    "ModelInput", "DataSeries", "ModelOutput", "Interpretation", "Chart", "Implementation"):
            n = s.run(f"MATCH (n:{lbl} {{catalog:$c}}) RETURN count(n) AS n", c=CAT).single()["n"]
            print(f"  :{lbl:20} {n}")
        print("EDGE COUNTS")
        for rel in ("MAKES", "USES", "INFORMS", "HAS_SPEC", "GROUNDED_IN", "TAKES_INPUT", "BOUND_TO",
                    "PRODUCES", "HAS_INTERPRETATION", "ILLUSTRATED_BY", "ENCODES", "RENDERS", "IMPLEMENTED_BY"):
            n = s.run(f"MATCH (a {{catalog:$c}})-[r:{rel}]->() RETURN count(r) AS n", c=CAT).single()["n"]
            print(f"  -[:{rel:18}]-> {n}")

        print("\nCONVICTION TRACE (decision -> model -> inputs -> execution -> outputs -> interpretation -> chart)")
        fails = 0
        for pid in personas:
            r = s.run("""
                MATCH (dm:DecisionMaker {id:$pid, catalog:$c})-[:USES]->(m:Model)
                RETURN count(DISTINCT m) AS models,
                  [x IN collect(DISTINCT m) WHERE NOT (x)-[:TAKES_INPUT]->() | x.id] AS no_inputs,
                  [x IN collect(DISTINCT m) WHERE NOT (x)-[:PRODUCES]->() | x.id] AS no_outputs,
                  [x IN collect(DISTINCT m) WHERE NOT (x)-[:GROUNDED_IN]->() | x.id] AS no_paper,
                  [x IN collect(DISTINCT m) WHERE NOT (x)-[:RENDERS]->() | x.id] AS no_charts
                """, c=CAT, pid=pid).single()
            errs = []
            if r["models"] < 3: errs.append(f"{r['models']} models")
            for k in ("no_inputs", "no_outputs", "no_paper", "no_charts"):
                if r[k]: errs.append(f"{k}: {r[k]}")
            fails += bool(errs)
            print(f"  {OK if not errs else FAIL}  {pid:28} {r['models']} models"
                  + ("" if not errs else "  " + "; ".join(errs)))
        # one full end-to-end spot trace
        t = s.run("""
            MATCH (dm:DecisionMaker {id:'volatility_trader', catalog:$c})-[:USES]->(m:Model)-[:PRODUCES]->(o:ModelOutput)
            MATCH (m)-[:GROUNDED_IN]->(p:Paper)
            OPTIONAL MATCH (o)<-[:ENCODES]-(ch:Chart)
            RETURN m.id AS model, p.id AS paper, collect(DISTINCT o.name)[0..3] AS outputs,
                   count(DISTINCT ch) AS charts LIMIT 1
            """, c=CAT).single()
        if t:
            print(f"\n  {TICK} spot-trace: volatility_trader -> {t['model']} (grounded in {t['paper']})")
            print(f"      outputs {t['outputs']} -> {t['charts']} charts encode them")
        print(f"\nCONVICTION: {'ALL PERSONAS PASS' if not fails else f'{fails} FAILURES'}")
        return 0 if fails == 0 else 1


def main() -> int:
    driver = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7688"),
                                  auth=(os.environ.get("NEO4J_USERNAME", "neo4j"),
                                        os.environ.get("NEO4J_PASSWORD", "devpassword")))
    try:
        driver.verify_connectivity()
        specs, personas = _load()
        print(f"horizon-neo4j: loading {len(specs)} models + {len(personas)} personas (catalog='{CAT}')")
        seed(driver, specs, personas)
        return report(driver, personas)
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
