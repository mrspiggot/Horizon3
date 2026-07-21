"""Assemble the canonical doc as markdown, and write the .md file.

`assemble_markdown()` is the single source both outputs share: the HTML renderer
converts the very same markdown. Narrative fragments supply prose (and the conceptual
diagrams that aren't code-derived); everything else is injected from the manifest.
"""
from __future__ import annotations

from pathlib import Path

from .manifest import MANIFEST_PATH, SystemManifest
from .tables import (capability_matrix, gates_table, graph_roster, prompt_catalogue,
                     spine_family, spine_gaps, spine_jurisdiction)

NARR = Path(__file__).resolve().parent / "narrative"
DEFAULT_MD = MANIFEST_PATH.parent / "agentic-system-design.generated.md"


def _frag(name: str) -> str:
    p = NARR / f"{name}.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _md_table(headers, rows) -> str:
    if not rows:
        return "_none_"
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def _graph(m: SystemManifest, name: str):
    return next((g for g in m.graphs if g.name == name), None)


def _diagram(mermaid: str, caption: str) -> str:
    return f"*{caption}*\n\n```mermaid\n{mermaid}\n```"


def _version_badge(m: SystemManifest) -> str:
    v = m.version
    return (f"> **Version** `{v.pyproject or '?'}` · commit `{v.git_sha or '?'}` "
            f"({v.branch or '?'}) · generated {v.generated_at or '?'}")


def _spine_section(m: SystemManifest) -> str:
    sp = m.spine
    if not sp.online:
        return f"> ⚠️ **Spine offline** when this doc was built ({sp.error or 'unreachable'}); census omitted."
    parts = [f"**{sp.executable_models}** executable-catalog models · "
             f"**{sp.proven_cells}** proven model×jurisdiction cells · "
             f"labels: {', '.join(f'`{x}`' for x in sp.labels)} · "
             f"relationships: {', '.join(f'`{x}`' for x in sp.rel_types)}"]
    parts.append("### Executable models by family\n\n" + _md_table(*spine_family(m)))
    parts.append("### Executable coverage by jurisdiction\n\n" + _md_table(*spine_jurisdiction(m)))
    if sp.gaps:
        parts.append("### Data gaps (roles missing in a jurisdiction)\n\n" + _md_table(*spine_gaps(m)))
    return "\n\n".join(parts)


def _schema_tables(m: SystemManifest) -> str:
    parts = ["### Structured-output schemas (the tool surface)"]
    for s in m.schemas:
        parts.append(f"**`{s.name}`** — `{s.module}`\n\n" +
                     _md_table(["Field", "Description"], [[f["name"], f["desc"] or "—"] for f in s.fields]))
    return "\n\n".join(parts)


def assemble_markdown(m: SystemManifest) -> str:
    parts = [
        _version_badge(m),
        _frag("00-hero"),
        _frag("10-firewall"),
        _frag("20-context"),
        _frag("30-graphs"),
        "### The graph roster\n\n" + _md_table(*graph_roster(m)),
    ]
    for name, cap in (("selector", "Model-Selection graph"),
                      ("judge", "Grounding Judge graph")):
        g = _graph(m, name)
        if g:
            parts.append(_diagram(g.mermaid, f"{cap} — {g.role}"))
    if m.ats.mermaid:
        parts.append(_diagram(m.ats.mermaid, "ATS commissioning orchestrator (not a StateGraph)"))

    parts.append(_frag("40-pipeline"))
    ag = _graph(m, "article_graph")
    if ag:
        parts.append(_diagram(ag.mermaid, "Article pipeline — extracted from the compiled graph"))

    parts.append(_frag("50-studio"))
    st = _graph(m, "studio")
    if st:
        parts.append(_diagram(st.mermaid, "Chart Studio state machine — extracted from the compiled graph"))
        parts.append("### Chart Studio — node capability matrix\n\n" + _md_table(*capability_matrix(st)))

    parts.append(_frag("60-spine"))
    parts.append(_spine_section(m))
    parts.append(_frag("70-prompts"))
    parts.append("### Prompt catalogue\n\n" + _md_table(*prompt_catalogue(m)))
    parts.append(_schema_tables(m))
    parts.append(_frag("80-gates"))
    parts.append("### Quality gates\n\n" + _md_table(*gates_table(m)))
    parts.append(_frag("90-footer"))
    return "\n\n".join(p for p in parts if p) + "\n"


def write_markdown(m: SystemManifest, path: Path = DEFAULT_MD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(assemble_markdown(m), encoding="utf-8")
    return path
