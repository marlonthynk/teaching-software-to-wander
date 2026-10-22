"""Simple lookups for the graph's tools: find nodes, read one in full, resolve a name.

The queries are in wander/graph/queries/lookups.cypher.
"""

from __future__ import annotations

from wander import filters
from wander.graph.db import Graph


def kind_of(node) -> str:
    return next(iter(node.labels))


def label_of(node) -> str:
    return node.get("name") or node.get("title") or node["id"]


def find(graph: Graph, kind: str | None = None, where: dict | None = None,
         name: str | None = None, limit: int = 50) -> dict:
    if kind is not None and kind not in graph.ontology.entities:
        raise ValueError(f"{kind} isn't a declared kind of thing. Declared: {', '.join(graph.ontology.entities)}.")
    filters.validate(where)
    rows = graph.run("lookups:find", kind=kind, name=name)
    hits = [r["n"] for r in rows if filters.matches(dict(r["n"]), where)]
    limit = max(1, min(int(limit), 200))
    return {"total": len(hits), "returned": min(limit, len(hits)),
            "nodes": [{"id": n["id"], "type": kind_of(n), "name": label_of(n),
                       **{k: v for k, v in sorted(dict(n).items()) if k not in ("id", "name", "title")}}
                      for n in hits[:limit]]}


def resolve(graph: Graph, ref: str):
    """A node by id, or by (unique) name."""
    rows = graph.run("lookups:resolve", ref=ref)
    exact = [r["n"] for r in rows if r["exact"]]
    if len(exact) == 1:
        return exact[0]
    if not exact and len(rows) == 1:
        return rows[0]["n"]
    if not rows:
        raise ValueError(f"Nothing called {ref!r}. Use find to look it up.")
    raise ValueError(f"{ref!r} matches several things: " +
                     ", ".join(f"{kind_of(r['n'])} {label_of(r['n'])} ({r['n']['id']})" for r in rows))


def get_details(graph: Graph, ref: str, edge_limit: int = 40) -> dict:
    node = resolve(graph, ref)
    rows = graph.run("lookups:details", id=node["id"])
    counts: dict[str, int] = {}
    edges = []
    for r in rows:
        if r["rel"] is None:
            continue
        key = f"{r['rel']}{'>' if r['outgoing'] else '<'}"
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= edge_limit:
            other = r["other"]
            edges.append({"relationship": r["rel"], "direction": "out" if r["outgoing"] else "in",
                          "other": {"id": other["id"], "type": kind_of(other), "name": label_of(other)},
                          **dict(r["props"])})
    for key, n in counts.items():
        if n > edge_limit:
            edges.append({"relationship": key[:-1], "more": n - edge_limit})
    return {"id": node["id"], "type": kind_of(node), "name": label_of(node),
            "properties": {k: v for k, v in sorted(dict(node).items()) if k != "id"},
            "edge_counts": counts, "edges": edges}
