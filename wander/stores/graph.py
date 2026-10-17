"""Graph stores. core.py talks to a GraphStore, never to Neo4j directly.

Two implementations over the same generated JSON:
- Neo4jStore: the real one. Every read runs in a read transaction.
- InMemoryStore: used by the tests, and by readers who can't run Neo4j (--store memory).

Both only contain what the ontology declares: undeclared types, relationships and
properties are filtered out when the data is loaded (see visible_data).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from wander.stores import filters
from wander.ontology import Ontology

GENERATED = Path(__file__).resolve().parents[2] / "data" / "generated"

# A pattern is a sequence of steps; each step is (relationship type, direction).
# ">" follows the relationship as declared (from -> to); "<" walks it backwards.
Step = tuple[str, str]
Pattern = tuple[Step, ...]


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    properties: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def label(self) -> str:
        p = self.properties
        return p.get("name") or p.get("title") or self.id


@dataclass(frozen=True)
class Hop:
    """One step out of a node: along `rel` in `direction`, to `other`."""
    rel: str
    direction: str
    other: str
    properties: dict = field(default_factory=dict, hash=False, compare=False)
    edge: int = field(default=-1, compare=False)  # which relationship (in-memory store only)


class GraphStore(Protocol):
    ontology: Ontology

    def get(self, node_id: str) -> Node | None: ...
    def get_many(self, node_ids: list[str]) -> dict[str, Node]: ...
    def neighbours(self, node_ids: list[str]) -> dict[str, list[Hop]]: ...
    def find(self, type_: str | None = None, where: dict | None = None,
             name: str | None = None, limit: int = 100) -> list[Node]: ...
    def count(self, type_: str) -> int: ...
    def pattern_reach(self, population: str, pattern: Pattern) -> dict[str, set[str]]: ...
    def pattern_paths(self, population: str, pattern: Pattern, end: str) -> list[list]: ...
    def reload(self, ontology: Ontology) -> None: ...


# ---------------------------------------------------------------------------
# Filtering the generated data through the ontology


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


def matches_name(node: Node, name: str) -> bool:
    return name.lower() in node.label.lower() or name.lower() == node.id.lower()


# ---------------------------------------------------------------------------
# In memory


class InMemoryStore:
    def __init__(self, ontology: Ontology | None = None, data_dir: Path | None = None):
        self.data_dir = data_dir
        self.reload(ontology or Ontology.load())

    def reload(self, ontology: Ontology) -> None:
        self.ontology = ontology
        nodes, edges = visible_data(ontology, *read_generated(self.data_dir))
        self.nodes = {n["id"]: Node(n["id"], n["type"], n["properties"]) for n in nodes}
        self.adj: dict[str, list[Hop]] = defaultdict(list)
        for i, e in enumerate(edges):
            self.adj[e["from"]].append(Hop(e["type"], ">", e["to"], e["properties"], i))
            self.adj[e["to"]].append(Hop(e["type"], "<", e["from"], e["properties"], i))
        self.n_edges = len(edges)

    def get(self, node_id):
        return self.nodes.get(node_id)

    def get_many(self, node_ids):
        return {i: self.nodes[i] for i in node_ids if i in self.nodes}

    def neighbours(self, node_ids):
        return {i: list(self.adj.get(i, [])) for i in node_ids}

    def find(self, type_=None, where=None, name=None, limit=100):
        filters.validate(where)
        out = [n for n in self.nodes.values()
               if (type_ is None or n.type == type_)
               and filters.matches(n.properties, where)
               and (name is None or matches_name(n, name))]
        return sorted(out, key=lambda n: n.id)[:limit]

    def count(self, type_):
        return sum(1 for n in self.nodes.values() if n.type == type_)

    def _walk(self, start: str, pattern: Pattern):
        """Every instance of the pattern from `start`, as [node, hop, node, ...].

        Like Cypher, a single path never uses the same relationship twice.
        """
        paths = [([start], frozenset())]
        for rel, direction in pattern:
            paths = [(path + [h, h.other], used | {h.edge})
                     for path, used in paths for h in self.adj.get(path[-1], [])
                     if h.rel == rel and h.direction == direction and h.edge not in used]
        return [path for path, _ in paths]

    def pattern_reach(self, population, pattern):
        reach: dict[str, set[str]] = defaultdict(set)
        for start in (n.id for n in self.nodes.values() if n.type == population):
            for path in self._walk(start, pattern):
                reach[path[-1]].add(start)
        return dict(reach)

    def pattern_paths(self, population, pattern, end):
        """Every instance of the pattern from a population node to `end`, as [node, hop, node, ...]."""
        # walk backwards from the end so we don't scan the whole population
        back = tuple((rel, "<" if d == ">" else ">") for rel, d in reversed(pattern))
        paths = []
        for rev in self._walk(end, back):
            if self.nodes[rev[-1]].type != population:
                continue
            nodes, hops = rev[::2][::-1], rev[1::2][::-1]
            path = [nodes[0]]
            for (rel, direction), h, nxt in zip(pattern, hops, nodes[1:]):
                path += [Hop(rel, direction, nxt, h.properties, h.edge), nxt]
            paths.append(path)
        return paths


# ---------------------------------------------------------------------------
# Neo4j


def neo4j_settings() -> tuple[str, str, str]:
    from dotenv import load_dotenv
    load_dotenv()
    return (os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "wanderwander"))


def cypher_pattern(pattern: Pattern, ontology: Ontology) -> str:
    """Turn a validated pattern into a Cypher path fragment, e.g. -[:RAISED]->()-[:ROUTED_TO]->.

    Relationship names can't be query parameters in Cypher, so each one is checked against the
    ontology (whose names are validated) before it goes anywhere near a query.
    """
    parts = []
    for i, (rel, direction) in enumerate(pattern):
        if rel not in ontology.relationships or direction not in "<>":
            raise ValueError(f"Unknown step {rel}{direction}")
        edge = f"-[r{i}:{rel}]->" if direction == ">" else f"<-[r{i}:{rel}]-"
        parts.append(edge + ("(n{})".format(i) if i < len(pattern) - 1 else ""))
    return "".join(parts)


class Neo4jStore:
    def __init__(self, ontology: Ontology | None = None, uri=None, user=None, password=None):
        from neo4j import GraphDatabase
        d_uri, d_user, d_password = neo4j_settings()
        self.driver = GraphDatabase.driver(uri or d_uri, auth=(user or d_user, password or d_password))
        self.ontology = ontology or Ontology.load()

    def close(self):
        self.driver.close()

    def reload(self, ontology: Ontology) -> None:
        from data.load_graph import load
        self.ontology = ontology
        load(ontology, self.driver)

    def _read(self, query: str, **params) -> list:
        with self.driver.session() as session:
            return session.execute_read(lambda tx: list(tx.run(query, **params)))

    @staticmethod
    def _node(record_node) -> Node:
        props = dict(sorted(dict(record_node).items()))  # same order as the in-memory store
        node_id = props.pop("id")
        return Node(node_id, next(iter(record_node.labels)), props)

    def get(self, node_id):
        return self.get_many([node_id]).get(node_id)

    def get_many(self, node_ids):
        rows = self._read("MATCH (n) WHERE n.id IN $ids RETURN n", ids=list(node_ids))
        return {(n := self._node(r["n"])).id: n for r in rows}

    def neighbours(self, node_ids):
        rows = self._read(
            "MATCH (n)-[r]-(m) WHERE n.id IN $ids "
            "RETURN n.id AS id, type(r) AS rel, startNode(r) = n AS out, m.id AS other, "
            "properties(r) AS props ORDER BY id, rel, other",
            ids=list(node_ids))
        out = {i: [] for i in node_ids}
        for r in rows:
            out[r["id"]].append(Hop(r["rel"], ">" if r["out"] else "<", r["other"], dict(sorted(r["props"].items()))))
        return out

    def find(self, type_=None, where=None, name=None, limit=100):
        filters.validate(where)
        if type_ is not None and type_ not in self.ontology.entities:
            return []
        label = f":{type_}" if type_ else ""
        rows = self._read(f"MATCH (n{label}) RETURN n ORDER BY n.id")
        nodes = [self._node(r["n"]) for r in rows]
        out = [n for n in nodes if filters.matches(n.properties, where)
               and (name is None or matches_name(n, name))]
        return out[:limit]

    def count(self, type_):
        if type_ not in self.ontology.entities:
            return 0
        return self._read(f"MATCH (n:{type_}) RETURN count(n) AS c")[0]["c"]

    def pattern_reach(self, population, pattern):
        if population not in self.ontology.entities:
            raise ValueError(f"Unknown type {population}")
        query = (f"MATCH (p:{population}){cypher_pattern(pattern, self.ontology)}(end) "
                 "RETURN end.id AS end, collect(DISTINCT p.id) AS starts")
        return {r["end"]: set(r["starts"]) for r in self._read(query)}

    def pattern_paths(self, population, pattern, end):
        if population not in self.ontology.entities:
            raise ValueError(f"Unknown type {population}")
        query = (f"MATCH path = (p:{population}){cypher_pattern(pattern, self.ontology)}(end {{id: $end}}) "
                 "RETURN [n IN nodes(path) | n.id] AS ids, "
                 "[r IN relationships(path) | properties(r)] AS props")
        paths = []
        for r in self._read(query, end=end):
            ids, props = r["ids"], r["props"]
            path = [ids[0]]
            for i, (rel, direction) in enumerate(pattern):
                path += [Hop(rel, direction, ids[i + 1], dict(sorted(props[i].items()))), ids[i + 1]]
            paths.append(path)
        return paths


def open_store(kind: str = "neo4j", ontology: Ontology | None = None) -> GraphStore:
    if kind == "memory":
        return InMemoryStore(ontology)
    if kind == "neo4j":
        return Neo4jStore(ontology)
    raise ValueError(f"Unknown store {kind}; use neo4j or memory.")
