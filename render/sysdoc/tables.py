"""Table builders — each returns (headers, rows) so the markdown and HTML renderers
share one source of truth for the auto-generated tables.

Everything here reads the manifest as dataclasses (from build_manifest); the renderers
handle formatting only.
"""
from __future__ import annotations

from .manifest import GraphInfo, SystemManifest

# temperatures are declared at call sites but get_llm ignores them at runtime
TEMP_NOTE = "declared (Opus 4.8 ignores at runtime)"
_KIND_LABEL = {"llm": "LLM", "vision": "VISION", "deterministic": "DET"}


def _flow(g: GraphInfo) -> str:
    return " → ".join(n.id for n in g.nodes)


def _temps(n) -> str:
    ts = [t for t in n.declared_temps if t is not None]
    return ", ".join(f"{t:g}" for t in ts) if ts else "—"


def graph_roster(m: SystemManifest):
    headers = ["Graph", "Package", "Role", "Nodes", "Flow", "LangSmith"]
    rows = [[g.name, g.package, g.role, str(len(g.nodes)), _flow(g), g.langsmith_project or "—"]
            for g in m.graphs]
    rows.append(["ats", m.ats.stages and "render/ats" or "render/ats",
                 "Commissioning (not a StateGraph)", str(len(m.ats.stages)),
                 " → ".join(m.ats.stages), "—"])
    return headers, rows


def capability_matrix(g: GraphInfo):
    headers = ["Node", "Kind", "Gate", "Schema", "Model", "Temp"]
    rows = []
    for n in g.nodes:
        rows.append([
            n.id, _KIND_LABEL.get(n.kind, n.kind), "yes" if n.is_gate else "—",
            ", ".join(n.schemas) or "—", ", ".join(n.models) or "—", _temps(n),
        ])
    return headers, rows


def prompt_catalogue(m: SystemManifest):
    headers = ["Graph", "Node", "Kind", "Schema", "Model", "Temp"]
    rows = []
    for g in m.graphs:
        for n in g.nodes:
            if n.kind in ("llm", "vision"):
                rows.append([g.name, n.id, _KIND_LABEL.get(n.kind, n.kind),
                             ", ".join(n.schemas) or "—", ", ".join(n.models) or "—", _temps(n)])
    return headers, rows


def gates_table(m: SystemManifest):
    headers = ["Graph", "Gate node", "Kind", "Routes to (conditional)"]
    rows = []
    for g in m.graphs:
        for n in g.nodes:
            if n.is_gate:
                targets = [e.target for e in g.edges if e.source == n.id and e.conditional]
                rows.append([g.name, n.id, _KIND_LABEL.get(n.kind, n.kind),
                             ", ".join(t.replace("__end__", "END") for t in targets) or "—"])
    return headers, rows


def spine_family(m: SystemManifest):
    headers = ["Model family", "Executable models"]
    rows = [[r["family"], str(r["count"])] for r in m.spine.by_family]
    return headers, rows


def spine_jurisdiction(m: SystemManifest):
    headers = ["Jurisdiction", "Currency", "Executable models"]
    rows = [[r["id"], r.get("ccy") or "—", str(r["models"])] for r in m.spine.by_jurisdiction]
    return headers, rows


def spine_gaps(m: SystemManifest):
    headers = ["Jurisdiction", "Missing role", "Models blocked"]
    rows = [[r["jurisdiction"], r["role"], ", ".join(r["models"])] for r in m.spine.gaps]
    return headers, rows
