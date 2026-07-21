"""Assemble a SystemManifest from the extractors.

Shared by `scripts/gen_sysdoc.py` (full build, with the live spine census) and
`scripts/check_sysdoc_drift.py` (code-only build, spine skipped by default — data
freshness is not code drift).
"""
from __future__ import annotations

from .extract_catalog import extract_catalog
from .extract_graphs import extract_all_graphs, extract_ats, load_annotations, referenced_schemas
from .extract_spine import extract_spine
from .manifest import SpineInfo, SystemManifest, version_stamp


def build_manifest(*, with_spine: bool = True) -> SystemManifest:
    annotations = load_annotations()
    graphs = extract_all_graphs(annotations)
    return SystemManifest(
        version=version_stamp(),
        graphs=graphs,
        ats=extract_ats(annotations),
        spine=extract_spine() if with_spine else SpineInfo(online=False, error="skipped (code-only build)"),
        catalog=extract_catalog(),
        schemas=referenced_schemas(graphs),
    )
