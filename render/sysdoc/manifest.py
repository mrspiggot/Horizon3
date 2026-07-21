"""The SystemManifest — the machine-truth data model, serialised to JSON.

This is the single diffable source of truth the renderers and the drift-gate read.
Everything here is plain data (dataclasses) so `asdict` round-trips to stable JSON.
The `version.generated_at` field is the ONLY non-deterministic field; the drift-gate
ignores the whole `version` block when comparing (it compares architecture, not when
the doc was built).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO / "docs" / "system" / "system_manifest.json"

SCHEMA_VERSION = 1  # bump when the manifest shape changes


@dataclass
class NodeInfo:
    id: str
    kind: str                       # llm | vision | deterministic | gate
    is_gate: bool = False           # source of a conditional edge
    schemas: list[str] = field(default_factory=list)   # structured-output classes
    models: list[str] = field(default_factory=list)    # resolved model constants
    declared_temps: list[float | None] = field(default_factory=list)


@dataclass
class EdgeInfo:
    source: str
    target: str
    conditional: bool = False


@dataclass
class GraphInfo:
    name: str
    package: str
    role: str = ""
    langsmith_project: str = ""
    nodes: list[NodeInfo] = field(default_factory=list)
    edges: list[EdgeInfo] = field(default_factory=list)
    mermaid: str = ""               # our styled, node-kind-coloured diagram
    mermaid_raw: str = ""           # LangGraph's own draw_mermaid(), for cross-check


@dataclass
class AtsInfo:
    """The ATS is a hand-coded orchestrator, not a StateGraph — modelled from
    annotations rather than auto-extracted."""
    stages: list[str] = field(default_factory=list)
    edges: list[EdgeInfo] = field(default_factory=list)
    note: str = ""
    mermaid: str = ""


@dataclass
class SpineInfo:
    online: bool = False
    error: str = ""
    executable_models: int = 0
    proven_cells: int = 0
    labels: list[str] = field(default_factory=list)
    rel_types: list[str] = field(default_factory=list)
    by_family: list[dict] = field(default_factory=list)        # {family, count}
    by_jurisdiction: list[dict] = field(default_factory=list)  # {id, ccy, models}
    gaps: list[dict] = field(default_factory=list)             # {jurisdiction, role, models}


@dataclass
class CatalogInfo:
    graph_models: int = 0     # catalog/graph/*.yaml  (executable-catalog)
    design_models: int = 0    # catalog/models/*.yaml (design-only)
    personas: int = 0


@dataclass
class SchemaInfo:
    name: str
    module: str
    fields: list[dict] = field(default_factory=list)   # {name, desc}


@dataclass
class VersionStamp:
    pyproject: str = ""
    git_sha: str = ""
    branch: str = ""
    commit_date: str = ""
    generated_at: str = ""


@dataclass
class SystemManifest:
    schema_version: int = SCHEMA_VERSION
    version: VersionStamp = field(default_factory=VersionStamp)
    graphs: list[GraphInfo] = field(default_factory=list)
    ats: AtsInfo = field(default_factory=AtsInfo)
    spine: SpineInfo = field(default_factory=SpineInfo)
    catalog: CatalogInfo = field(default_factory=CatalogInfo)
    schemas: list[SchemaInfo] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def write(self, path: Path = MANIFEST_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _pyproject_version() -> str:
    pp = REPO / "pyproject.toml"
    if not pp.exists():
        return ""
    try:
        import tomllib
        return tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {}).get("version", "")
    except Exception:
        # cheap fallback: scan for a version = "..." line under [project]
        for line in pp.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("version") and "=" in s:
                return s.split("=", 1)[1].strip().strip('"').strip("'")
        return ""


def version_stamp() -> VersionStamp:
    """Stamp the manifest. No git tags exist in this repo, so we use the short SHA
    (never `git describe --tags`, which would fail)."""
    return VersionStamp(
        pyproject=_pyproject_version(),
        git_sha=_git("rev-parse", "--short", "HEAD"),
        branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
        commit_date=_git("log", "-1", "--format=%cI"),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Load a committed manifest as a plain dict (for the drift-gate / diff)."""
    return json.loads(path.read_text(encoding="utf-8"))
