"""The connection to Neo4j, and how the wander's queries are run.

Every query lives in a .cypher file in wander/graph/queries/ — the same files you can paste
into Neo4j Browser. This module only loads a file, fills in the parameters, and runs it in a
read-only transaction, so even a buggy query can't change the graph. The only writes are the
loader (data/load_graph.py), when a developer applies ontology changes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from wander.ontology import Ontology

QUERIES = Path(__file__).resolve().parent / "queries"


def settings() -> tuple[str, str, str]:
    load_dotenv()
    return (os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "wanderwander"))


def cypher(name: str, **numbers: int) -> str:
    """The text of a query file — or of one named block in lookups.cypher (e.g. 'lookups:find').

    Cypher can't take a path length (the 5 in [*1..5]) as a parameter, so those are written
    into the text here, as __MAX_HOPS__ etc. They're checked to be small whole numbers first.
    """
    file, _, block = name.partition(":")
    text = (QUERIES / f"{file}.cypher").read_text()
    if block:
        text = re.split(rf"^// name: {re.escape(block)}\s*$", text, flags=re.M)[1].split("// name:")[0]
    for key, value in numbers.items():
        if not isinstance(value, int) or not 1 <= value <= 8:
            raise ValueError(f"{key} must be a whole number from 1 to 8.")
        text = text.replace(f"__{key.upper()}__", str(value))
    return text.strip().rstrip(";")


class Graph:
    """Neo4j, plus the ontology that says what's in it."""

    def __init__(self, ontology: Ontology | None = None):
        uri, user, password = settings()
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.ontology = ontology or Ontology.load()

    def run(self, query_name: str, numbers: dict | None = None, /, **params) -> list:
        """Run a query file in a read transaction. Rows keep Neo4j's own node and relationship
        objects, so labels and directions are there for the Python that reads them."""
        query = cypher(query_name, **(numbers or {}))
        with self.driver.session() as session:
            return session.execute_read(lambda tx: list(tx.run(query, **params)))

    def reload(self, ontology: Ontology) -> None:
        """Reload Neo4j from the generated data, through this ontology (a developer applied changes)."""
        from data.load_graph import load
        load(ontology, self.driver)
        self.ontology = ontology

    def close(self) -> None:
        self.driver.close()
