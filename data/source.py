"""The generated company data, seen through an ontology.

Both stores are loaded from the same JSON in data/generated/. The graph only gets what the
ontology declares: undeclared kinds of thing, relationships and properties are left out.
"""

from __future__ import annotations

import json
from pathlib import Path

from wander.ontology import Ontology

GENERATED = Path(__file__).resolve().parent / "generated"


def read_generated(data_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    data_dir = Path(data_dir or GENERATED)
    return (json.loads((data_dir / "nodes.json").read_text()),
            json.loads((data_dir / "edges.json").read_text()))


def visible_data(ontology: Ontology, nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Only what the ontology declares: node types, their properties, relationships and theirs."""
    kept_nodes, types = [], {}
    for n in nodes:
        entity = ontology.entities.get(n["type"])
        if entity is None:
            continue
        props = {k: v for k, v in n["properties"].items() if k in entity.properties}
        kept_nodes.append({"id": n["id"], "type": n["type"], "properties": props})
        types[n["id"]] = n["type"]
    kept_edges = []
    for e in edges:
        rel = ontology.relationships.get(e["type"])
        if rel is None or types.get(e["from"]) != rel.from_ or types.get(e["to"]) != rel.to:
            continue
        props = {k: v for k, v in e["properties"].items() if k in rel.properties}
        kept_edges.append({"type": e["type"], "from": e["from"], "to": e["to"], "properties": props})
    return kept_nodes, kept_edges
