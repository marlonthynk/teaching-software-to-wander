import shutil

import pytest

from wander.ontology import INITIAL_PATH, Ontology
from wander.stores.graph import InMemoryStore


@pytest.fixture
def ontology_file(tmp_path, monkeypatch):
    """A temporary copy of the initial ontology. Tests never touch the real ontology.yaml."""
    path = tmp_path / "ontology.yaml"
    shutil.copyfile(INITIAL_PATH, path)
    monkeypatch.setenv("WANDER_ONTOLOGY", str(path))
    return path


@pytest.fixture
def store(ontology_file):
    return InMemoryStore(Ontology.load(ontology_file))


@pytest.fixture
def q3_churners(store):
    return [n.id for n in store.find(type_="Customer", where={"churned_at": {"gte": "2026-07-01",
                                                                            "lte": "2026-09-30"}})]
