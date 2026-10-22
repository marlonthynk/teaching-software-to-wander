"""Shared test setup.

Tests that touch the graph need Neo4j running (docker compose up -d); without it they're
skipped with a message. They start from the initial ontology and, when they're done, reload
Neo4j through the live ontology.yaml, so the demo is left as it was.
"""

import shutil

import pytest

from wander import tools
from wander.ontology import INITIAL_PATH, ROOT, Ontology


@pytest.fixture(scope="session")
def graph():
    from wander.graph.db import Graph
    try:
        g = Graph(Ontology.load(INITIAL_PATH))
        g.driver.verify_connectivity()
    except Exception as e:  # Neo4j isn't running
        pytest.skip(f"Neo4j isn't reachable ({e.__class__.__name__}). Start it with: docker compose up -d")
    g.reload(Ontology.load(INITIAL_PATH))
    yield g
    g.reload(Ontology.load(ROOT / "ontology.yaml"))
    g.close()


@pytest.fixture
def ontology_file(tmp_path, monkeypatch):
    """A temporary copy of the initial ontology. Tests never touch the real ontology.yaml."""
    path = tmp_path / "ontology.yaml"
    shutil.copyfile(INITIAL_PATH, path)
    monkeypatch.setenv("WANDER_ONTOLOGY", str(path))
    return path


@pytest.fixture
def ctx(ontology_file, graph):
    """A tools context against the temporary ontology. Whatever a test applies to Neo4j is undone."""
    context = tools.Context()
    yield context
    graph.reload(Ontology.load(INITIAL_PATH))


@pytest.fixture
def q3_churners(graph):
    from wander.graph.lookups import find
    found = find(graph, "Customer", {"churned_at": {"gte": "2026-07-01", "lte": "2026-09-30"}})
    return [n["id"] for n in found["nodes"]]
