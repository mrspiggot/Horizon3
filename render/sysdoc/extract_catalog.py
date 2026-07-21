"""Catalog census — counts from the YAML source of truth (no DB needed).

`catalog/graph/*.yaml` are the executable-catalog models (seed the spine + drive
execution); `catalog/models/*.yaml` are design-only; personas live in a personas.yaml.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .manifest import CatalogInfo

REPO = Path(__file__).resolve().parents[2]


def _model_yamls(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return [p for p in sorted(d.glob("*.yaml"))
            if p.name != "personas.yaml" and not p.name.startswith("_")]


def _persona_count() -> int:
    for cand in (REPO / "catalog" / "graph" / "personas.yaml", REPO / "catalog" / "personas.yaml"):
        if cand.exists():
            try:
                data = yaml.safe_load(cand.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                # personas.yaml is usually {persona_id: {...}} or {personas: [...]}
                if "personas" in data and isinstance(data["personas"], (list, dict)):
                    return len(data["personas"])
                return len(data)
            if isinstance(data, list):
                return len(data)
    return 0


def extract_catalog() -> CatalogInfo:
    return CatalogInfo(
        graph_models=len(_model_yamls(REPO / "catalog" / "graph")),
        design_models=len(_model_yamls(REPO / "catalog" / "models")),
        personas=_persona_count(),
    )
