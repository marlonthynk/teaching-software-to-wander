"""Load the generated JSON into Neo4j, through the ontology.

    uv run python -m data.load_graph

Only declared node types, relationships and properties are loaded. This and the ontology
reload are the only places that write to Neo4j.
"""

from __future__ import annotations

import re
from collections import defaultdict

from data.source import read_generated, visible_data
from wander.ontology import Ontology


def load(ontology: Ontology | None = None, driver=None) -> dict:
    ontology = ontology or Ontology.load()
    nodes, edges = visible_data(ontology, *read_generated())
    own_driver = driver is None
    if own_driver:
        from neo4j import GraphDatabase

        from wander.graph.db import settings
        uri, user, password = settings()
        driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        by_label: dict[str, list] = defaultdict(list)
        for n in nodes:
            by_label[n["type"]].append({"id": n["id"], "props": n["properties"]})
        by_type: dict[str, list] = defaultdict(list)
        for e in edges:
            by_type[e["type"]].append({"from": e["from"], "to": e["to"], "props": e["properties"]})

        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
            # Labels and relationship types come from the validated ontology, never from users.
            # Keep Neo4j's schema in step with the ontology: drop the id constraints of entity
            # types it no longer declares (e.g. after a reset), then add any it now does.
            for name in stale_constraints(session, ontology):
                session.run(f"DROP CONSTRAINT {name} IF EXISTS").consume()
            for label in ontology.entities:
                session.run(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE").consume()

            def write(tx):
                for label, rows in by_label.items():
                    tx.run(f"UNWIND $rows AS row CREATE (n:{label}) SET n = row.props, n.id = row.id",
                           rows=rows).consume()
                for rel, rows in by_type.items():
                    tx.run(f"UNWIND $rows AS row MATCH (a {{id: row.from}}), (b {{id: row.to}}) "
                           f"CREATE (a)-[r:{rel}]->(b) SET r = row.props", rows=rows).consume()

            session.execute_write(write)
    finally:
        if own_driver:
            driver.close()
    return {"nodes": len(nodes), "edges": len(edges)}


def stale_constraints(session, ontology: Ontology) -> list[str]:
    """Our id constraints (named <label>_id) on labels the ontology no longer declares."""
    rows = session.run("SHOW CONSTRAINTS YIELD name, labelsOrTypes").data()
    return find_stale(rows, ontology)


def find_stale(rows: list[dict], ontology: Ontology) -> list[str]:
    declared = set(ontology.entities)
    return sorted(r["name"] for r in rows
                  if re.fullmatch(r"[a-z][a-z0-9]*_id", r["name"] or "")
                  and r["name"] == f"{(r['labelsOrTypes'] or [''])[0].lower()}_id"
                  and (r["labelsOrTypes"] or [""])[0] not in declared)


if __name__ == "__main__":
    counts = load()
    print(f"Loaded {counts['nodes']} nodes and {counts['edges']} relationships into Neo4j.")
