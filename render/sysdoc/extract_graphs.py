"""Extract the LangGraph DAGs (DB-free) into styled manifest entries.

`build_graph().get_graph()` gives the authoritative nodes/edges (with a `conditional`
flag per edge). We colour each node by its AST-inferred kind (llm/vision/deterministic)
and draw gates — nodes that are the source of a conditional edge — as hexagons, then
emit our own mermaid (so diagrams are auto-structure AND auto-styled). LangGraph's own
`draw_mermaid()` is kept alongside as `mermaid_raw` for cross-checking.

Only 4 of the 5 components are StateGraphs; the ATS is handled from annotations.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml

from .extract_prompts import index_schemas, node_func_map, node_llm_info
from .manifest import AtsInfo, EdgeInfo, GraphInfo, NodeInfo, SchemaInfo

_ANNOTATIONS_PATH = Path(__file__).resolve().parent / "annotations.yaml"


def load_annotations() -> dict:
    if _ANNOTATIONS_PATH.exists():
        return yaml.safe_load(_ANNOTATIONS_PATH.read_text(encoding="utf-8")) or {}
    return {}

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

START, END = "__start__", "__end__"

# Code-level registry of the LangGraph graphs (name → how to load + how to present).
GRAPHS = [
    {"name": "article_graph", "module": "render.article_graph.graph", "package": "render/article_graph",
     "role": "Orchestrator — assemble the whole artifact", "langsmith": "horizon3-article", "direction": "TB"},
    {"name": "selector", "module": "render.selector.graph", "package": "render/selector",
     "role": "Role 2 — which models to run", "langsmith": "", "direction": "LR"},
    {"name": "studio", "module": "render.studio.graph", "package": "render/studio",
     "role": "How to visualize an insight", "langsmith": "horizon3-chart-studio", "direction": "LR"},
    {"name": "judge", "module": "render.judge.graph", "package": "render/judge",
     "role": "Role 7 — is the prose true?", "langsmith": "", "direction": "LR"},
]

_MERMAID_INIT = ("%%{init:{'theme':'base','themeVariables':{'fontFamily':'Helvetica,Arial,sans-serif',"
                 "'fontSize':'14px','primaryColor':'#eef2f7','primaryBorderColor':'#1A2238',"
                 "'primaryTextColor':'#1A2238','lineColor':'#54617a'}}}%%")

_CLASSDEFS = [
    "classDef llm fill:#e8e7fb,stroke:#5b57c7,color:#2a2870;",
    "classDef vis fill:#dcefef,stroke:#2a8f8f,color:#124d4d;",
    "classDef det fill:#e6ebf3,stroke:#5b6b86,color:#2b3750;",
    "classDef term fill:#1A2238,stroke:#1A2238,color:#ffffff;",
]
_KIND_CLASS = {"llm": "llm", "vision": "vis", "deterministic": "det"}


def _node_shape(node: NodeInfo) -> str:
    """The mermaid node declaration for one node (hexagon if it's a gate)."""
    cls = _KIND_CLASS.get(node.kind, "det")
    if node.is_gate:
        return f'  {node.id}{{{{"{node.id}"}}}}:::{cls}'
    return f'  {node.id}["{node.id}"]:::{cls}'


def _styled_mermaid(name: str, direction: str, nodes: list[NodeInfo],
                    edges: list[EdgeInfo]) -> str:
    lines = [_MERMAID_INIT, f"flowchart {direction}"]
    lines.append(f'  {START}((start)):::term')
    for n in nodes:
        lines.append(_node_shape(n))
    lines.append(f'  {END}((end)):::term')
    for e in edges:
        arrow = "-.->" if e.conditional else "-->"
        lines.append(f"  {e.source} {arrow} {e.target}")
    lines.extend("  " + c for c in _CLASSDEFS)
    return "\n".join(lines)


def _gate_sources(edges: list[EdgeInfo]) -> set[str]:
    return {e.source for e in edges if e.conditional}


def extract_graph(meta: dict, annotations: dict) -> GraphInfo:
    mod = importlib.import_module(meta["module"])
    compiled = mod.build_graph()
    g = compiled.get_graph()

    raw_nodes = [n for n in g.nodes if n not in (START, END)]
    edges = [EdgeInfo(e.source, e.target, bool(getattr(e, "conditional", False))) for e in g.edges]
    edges.sort(key=lambda e: (e.source, e.target))
    gates = _gate_sources(edges)

    ast_info = node_llm_info(meta["package"])
    func_map = node_func_map(meta["package"])   # node id → function name (may differ)
    kind_overrides = (annotations.get("node_kind_overrides", {}) or {}).get(meta["name"], {}) or {}

    nodes: list[NodeInfo] = []
    for nid in raw_nodes:
        info = ast_info.get(func_map.get(nid, nid), {})
        kind = kind_overrides.get(nid) or info.get("kind", "deterministic")
        nodes.append(NodeInfo(
            id=nid, kind=kind, is_gate=(nid in gates),
            schemas=info.get("schemas", []) or [],
            models=info.get("models", []) or [],
            declared_temps=info.get("declared_temps", []) or [],
        ))

    gi = GraphInfo(
        name=meta["name"], package=meta["package"], role=meta["role"],
        langsmith_project=meta["langsmith"], nodes=nodes, edges=edges,
        mermaid=_styled_mermaid(meta["name"], meta["direction"], nodes, edges),
        mermaid_raw=g.draw_mermaid(),
    )
    return gi


def extract_all_graphs(annotations: dict) -> list[GraphInfo]:
    return [extract_graph(meta, annotations) for meta in GRAPHS]


def extract_ats(annotations: dict) -> AtsInfo:
    """Model the hand-coded ATS orchestrator from annotations (it is not a StateGraph)."""
    a = annotations.get("ats", {}) or {}
    stages_raw = a.get("stages", []) or []
    nodes = [NodeInfo(id=s["id"], kind=s.get("kind", "deterministic"),
                      is_gate=bool(s.get("is_gate", False))) for s in stages_raw]
    edges = [EdgeInfo(nodes[i].id, nodes[i + 1].id, False) for i in range(len(nodes) - 1)]
    if nodes:
        edges = [EdgeInfo(START, nodes[0].id, False), *edges, EdgeInfo(nodes[-1].id, END, False)]
    mermaid = _styled_mermaid("ats", a.get("direction", "LR"), nodes, edges)
    return AtsInfo(stages=[n.id for n in nodes], edges=edges, note=a.get("note", ""),
                   mermaid=mermaid)


def referenced_schemas(graphs: list[GraphInfo]) -> list[SchemaInfo]:
    """The structured-output schemas any node references, resolved to their defs."""
    idx = index_schemas()
    names: set[str] = set()
    for g in graphs:
        for n in g.nodes:
            names.update(n.schemas)
    out: list[SchemaInfo] = []
    for name in sorted(names):
        entry = idx.get(name)
        if entry:
            out.append(SchemaInfo(name=name, module=entry["module"], fields=entry["fields"]))
        else:
            out.append(SchemaInfo(name=name, module="(unresolved)", fields=[]))
    return out
