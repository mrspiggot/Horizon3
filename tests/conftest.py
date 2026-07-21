"""Test-wide configuration.

The runtime source of jurisdiction facts is Neo4j in production (render.jurisdiction_facts). The test
suite must run with NO live graph, so we pin the provider to `catalog` mode — it reads the same seed YAML
(catalog/jurisdictions.yaml) through the identical normaliser, so the two readers converge. A
`@pytest.mark.neo4j` parity test asserts they agree against a seeded graph.
"""
import os

import pytest

os.environ.setdefault("HORIZON3_JUR_SOURCE", "catalog")


def pytest_configure(config):
    config.addinivalue_line("markers", "neo4j: requires a live, seeded Neo4j spine (skipped by default)")
