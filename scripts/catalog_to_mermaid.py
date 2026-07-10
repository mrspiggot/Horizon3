#!/usr/bin/env python
"""Generate mermaid diagrams FROM the catalog YAML (so diagrams never drift from source).

Emits, into the output dir (arg 1, default ./diagrams):
  00-spine-overview.mmd   — personas ⇄ models (the M:N USES join; impl vs stub)
  <model_id>.mmd          — one per model: inputs → model → outputs, with §10 order + horizon

Render with mermaid-cli, e.g.:
  mmdc -i diagrams/rate_divergence.mmd -o diagrams/rate_divergence.svg -b white
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO / "catalog" / "models"
PERSONAS_FILE = REPO / "catalog" / "personas.yaml"

CLASSDEFS = """  classDef persona fill:#e0e7ff,stroke:#4338ca,color:#1e1b4b;
  classDef impl fill:#dcfce7,stroke:#16a34a,color:#14532d;
  classDef stub fill:#fef9c3,stroke:#ca8a04,color:#713f12;
  classDef inp fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
  classDef out fill:#f3e8ff,stroke:#9333ea,color:#4a044e;
  classDef derived fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;"""


def esc(s: str) -> str:
    """Make a string safe inside a mermaid "..." label."""
    return str(s).replace('"', "'").replace("\n", " ").strip()


def load_models() -> dict[str, dict]:
    return {f.stem: yaml.safe_load(f.read_text()) for f in sorted(MODELS_DIR.glob("*.yaml"))}


def is_stub(doc: dict) -> bool:
    return doc.get("build_stub") is True


def model_node(doc: dict) -> str:
    impl = doc.get("implemented_by", "")
    fn = impl.split(".")[-1] if impl else "build_stub (D5)"
    return f'{esc(doc.get("name", doc["model_id"]))}<br/><i>{esc(fn)}</i>'


def spine_overview(models: dict[str, dict], personas: list[dict]) -> str:
    lines = ["flowchart LR", CLASSDEFS, ""]
    # model nodes
    for mid, doc in models.items():
        cls = "stub" if is_stub(doc) else "impl"
        badge = "⏳" if is_stub(doc) else "✅"
        lines.append(f'  {mid}["{badge} {esc(doc.get("name", mid))}"]:::{cls}')
    lines.append("")
    # persona nodes + edges
    for p in personas:
        pid = p["persona_id"]
        uses = p.get("uses", []) or []
        label = f'{esc(p.get("name", pid))}<br/><small>{esc(p.get("decision", ""))}</small>'
        if not uses:
            label += "<br/><i>(models pending)</i>"
        lines.append(f'  {pid}["{label}"]:::persona')
        for u in uses:
            # solid edge from the persona that owns the exemplar, dotted "shares" for the rest
            if pid == "macro_rates_trader":
                lines.append(f"  {pid} --> {u}")
            else:
                lines.append(f'  {pid} -.->|shares| {u}')
    return "\n".join(lines) + "\n"


def model_diagram(doc: dict) -> str:
    mid = doc["model_id"]
    lines = ["flowchart LR", CLASSDEFS, ""]
    # inputs — now ROLE-based (bound per jurisdiction in jurisdictions.yaml)
    for i, inp in enumerate(doc.get("inputs", []) or []):
        req = "required" if inp.get("required") else "optional"
        cls = "inp" if inp.get("required") else "derived"
        label = (
            f'role: {esc(inp.get("role"))}<br/>'
            f'<small>{req} · {esc(inp.get("order"))} · @{esc(inp.get("horizon"))}</small>'
        )
        lines.append(f'  I{i}["{label}"]:::{cls}')
    # model + generalization badge
    cls = "stub" if is_stub(doc) else "impl"
    claimed = doc.get("jurisdictions", []) or []
    covers = (doc.get("implementation_coverage") or {}).get("covers", []) or []
    lines.append(f'  M["{model_node(doc)}"]:::{cls}')
    jlabel = (f'🌍 generic over {esc(", ".join(doc.get("generic_over", []) or ["—"]))}'
              f'<br/>DATA: {esc(" ".join(claimed) or "—")}'
              f'<br/>IMPL: {esc(" ".join(covers) or "none (build)")}')
    lines.append(f'  J["{jlabel}"]:::persona')
    lines.append("  M -.-> J")
    # outputs
    for j, out in enumerate(doc.get("outputs", []) or []):
        label = f'{esc(out.get("name"))}<br/><small>{esc(out.get("unit"))}</small>'
        lines.append(f'  O{j}["{label}"]:::out')
    lines.append("")
    # edges
    for i, _ in enumerate(doc.get("inputs", []) or []):
        lines.append(f"  I{i} --> M")
    for j, _ in enumerate(doc.get("outputs", []) or []):
        lines.append(f"  M --> O{j}")
    # interpretation as a note-ish trailing node
    interp = esc(doc.get("interpretation", ""))
    if interp:
        if len(interp) > 240:
            interp = interp[:237] + "…"
        lines.append(f'  N["📣 {interp}"]')
        lines.append("  class N persona")
        lines.append("  M -.-> N")
    return "\n".join(lines) + "\n"


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (REPO / "diagrams")
    out_dir.mkdir(parents=True, exist_ok=True)
    models = load_models()
    personas = yaml.safe_load(PERSONAS_FILE.read_text()).get("personas", [])

    (out_dir / "00-spine-overview.mmd").write_text(spine_overview(models, personas))
    for mid, doc in models.items():
        (out_dir / f"{mid}.mmd").write_text(model_diagram(doc))

    print(f"wrote {1 + len(models)} .mmd files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
