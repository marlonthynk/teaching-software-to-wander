"""The two toolsets, defined once. Used unchanged by the chat app, the MCP servers and the CLI.

Neither toolset can change the ontology: that happens in the viewer (proposals) and on its
Review page (a developer applies them). See wander/proposals.py.

Records: an ordinary store (search, get one record, filtered listing).
Graph:   the same data as a graph, with a server-side wander.

Descriptions are short, in the same tone for both sets, and say nothing about what the
data contains.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from wander import core
from wander.ontology import Ontology, OntologyError, ontology_path
from wander.stores.graph import GraphStore, open_store
from wander.stores.records import TABLES, RecordsError, RecordsStore


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., dict]
    step_title: Callable[[dict, dict], str]

    def api_spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


class Context:
    """What the tools run against. Opened lazily, so a Records-only process never needs Neo4j."""

    def __init__(self, store_kind: str | None = None, records_path=None):
        self.store_kind = store_kind or os.environ.get("WANDER_STORE", "neo4j")
        self.records_path = records_path
        self._graph: GraphStore | None = None
        self._records: RecordsStore | None = None
        self._ontology_version: int | None = None

    @property
    def graph(self) -> GraphStore:
        """The graph store, kept in step with ontology.yaml.

        The ontology can change from another process (the viewer, the CLI, another chat), so
        each use checks the file. Neo4j is shared, so only the declared types need refreshing;
        the in-memory store holds its own copy of the data, so it reloads.
        """
        version = ontology_path().stat().st_mtime_ns
        if self._graph is None:
            self._graph = open_store(self.store_kind, Ontology.load())
        elif version != self._ontology_version:
            onto = Ontology.load()
            if self.store_kind == "memory":
                self._graph.reload(onto)
            else:
                self._graph.ontology = onto
        self._ontology_version = version
        return self._graph

    @property
    def records(self) -> RecordsStore:
        if self._records is None:
            self._records = RecordsStore(self.records_path)
        return self._records


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


FILTERS_HELP = ('Filters on the record\'s own fields: {"field": value} for equality, or '
                '{"field": {"gte": ..., "lte": ...}} for a range (dates are YYYY-MM-DD).')

# ---------------------------------------------------------------------------
# Records toolset


def _search(ctx: Context, query: str, type: str | None = None, limit: int = 10) -> dict:
    hits = ctx.records.search(query, type, limit)
    return {"query": query, "results": hits}


def _get_record(ctx: Context, id: str) -> dict:
    record = ctx.records.get_record(id)
    if record is None:
        raise RecordsError(f"No record with id {id}.")
    return record


def _list_records(ctx: Context, type: str, filters: dict | None = None, limit: int = 25) -> dict:
    return ctx.records.list_records(type, filters, limit)


RECORD_FIELDS = "; ".join(f"{t}: {', '.join(['id'] + cols)}" for t, cols in TABLES.items())

RECORDS_TOOLS = [
    Tool(
        "search",
        "Keyword search across the company's records: customers (CRM), support tickets, documents "
        "(including comments on them), people and decisions. Any of the words may match; best "
        "matches first. Returns ids and short snippets; use get_record for the full record.",
        _obj({"query": {"type": "string", "description": "Words to search for."},
              "type": {"type": "string", "enum": list(TABLES), "description": "Only this record type."},
              "limit": {"type": "integer", "description": "At most this many results (default 10, max 50)."}},
             ["query"]),
        _search,
        lambda a, r: f"search “{a.get('query')}” ({len(r.get('results', []))} results)",
    ),
    Tool(
        "get_record",
        "Get one record's own fields by id.",
        _obj({"id": {"type": "string", "description": "The record id, e.g. cust_014 or tkt_0042."}}, ["id"]),
        _get_record,
        lambda a, r: f"get record {a.get('id')}",
    ),
    Tool(
        "list_records",
        "List records of one type, optionally filtered on their own fields. " + FILTERS_HELP +
        f" Fields by type — {RECORD_FIELDS}.",
        _obj({"type": {"type": "string", "enum": list(TABLES)},
              "filters": {"type": "object", "description": FILTERS_HELP},
              "limit": {"type": "integer", "description": "At most this many records (default 25, max 100)."}},
             ["type"]),
        _list_records,
        lambda a, r: f"list {a.get('type')} {json.dumps(a.get('filters') or {})} "
                     f"({r.get('total', 0)} found)",
    ),
]

# ---------------------------------------------------------------------------
# Graph toolset


def _wander(ctx: Context, anchors: list[str]) -> dict:
    # Hops, support and lift stay at the server's defaults: the guardrails aren't Claude's to
    # loosen, and the same starting points always give the same context. The CLI has the knobs.
    return core.wander(ctx.graph, anchors)


def _wander_title(a: dict, r: dict) -> str:
    s = r.get("stats", {})
    kind = (r.get("anchors") or [{}])[0].get("type", "node").lower()
    n = len(r.get("anchors", []))
    return (f"wander from {n} {kind}{'s' if n != 1 else ''} ({r.get('settings', {}).get('max_hops')} hops, "
            f"{s.get('nodes_returned', 0)} nodes kept, {len(r.get('pruned', []))} candidates pruned)")


def _base_rate(ctx: Context, node: str, since: str | None = None, outcome: str = "churned",
               pattern: str | None = None) -> dict:
    return core.compare_base_rate(ctx.graph, node, pattern=pattern, since=since, outcome=outcome)


def _details(ctx: Context, node: str) -> dict:
    return core.get_details(ctx.graph, node)


def _find(ctx: Context, type: str | None = None, filters: dict | None = None,
          name: str | None = None, limit: int = 50) -> dict:
    return core.find(ctx.graph, type, filters, name, limit)


def _view_ontology(ctx: Context) -> dict:
    onto = Ontology.load()
    return {"ontology": onto.describe()}


GRAPH_TOOLS = [
    Tool(
        "wander",
        "Start from one or more things of the same kind (e.g. customers) and walk outwards through "
        "everything they are connected to, following every relationship the ontology declares. "
        "The tool does the walking and the pruning: it returns the nodes the starting points "
        "converge on more than chance would explain, the paths that lead there, what lies behind "
        "each one, who else shares the same thread, and what it pruned and why. Use find first "
        "to get the starting ids.",
        _obj({"anchors": {"type": "array", "items": {"type": "string"}, "description": "Starting node ids."}},
             ["anchors"]),
        _wander,
        _wander_title,
    ),
    Tool(
        "compare_base_rate",
        "Compare how often an outcome happens for things connected to a node versus everything "
        "else, e.g. the churn rate of customers connected to X against all other customers. "
        "Optionally count only connections dated on or after a date. A signal, not proof.",
        _obj({"node": {"type": "string", "description": "Node id or name."},
              "since": {"type": "string", "description": "Only connections dated on or after this date (YYYY-MM-DD)."},
              "outcome": {"type": "string",
                          "description": "The outcome to count: a status value such as 'churned', or field=value."},
              "pattern": {"type": "string",
                          "description": "Optional: the path to the node, as wander shows it. Defaults to the shortest."}},
             ["node"]),
        _base_rate,
        lambda a, r: f"base rate for {a.get('node')}" + (f" since {a['since']}" if a.get("since") else "")
                     + (f": {r['with']['outcome']}/{r['with']['count']} vs {r['without']['outcome']}/"
                        f"{r['without']['count']}" if "with" in r else ""),
    ),
    Tool(
        "get_details",
        "Get one node in full: all its properties and its immediate connections, with their "
        "properties (e.g. the full text of a comment).",
        _obj({"node": {"type": "string", "description": "Node id or name."}}, ["node"]),
        _details,
        lambda a, r: f"details of {r.get('type', '')} {r.get('name', a.get('node'))}",
    ),
    Tool(
        "find",
        "Look up nodes by type, by filters on their properties, or by name. " + FILTERS_HELP,
        _obj({"type": {"type": "string", "description": "Entity type, e.g. Customer. See view_ontology."},
              "filters": {"type": "object", "description": FILTERS_HELP},
              "name": {"type": "string", "description": "Part of the name or title."},
              "limit": {"type": "integer", "description": "At most this many (default 50)."}}),
        _find,
        lambda a, r: f"find {a.get('type') or ''} {json.dumps(a.get('filters') or {})} "
                     f"{a.get('name') or ''}".replace("  ", " ") + f"({r.get('total', 0)} found)",
    ),
    Tool(
        "view_ontology",
        "Show which kinds of things the graph knows about, how they connect, and what each means "
        "for the business, plus the log of changes. The ontology is read-only here: people add to "
        "it from the ontology viewer, and a developer reviews and applies their proposals.",
        _obj({}),
        _view_ontology,
        lambda a, r: "view ontology",
    ),
]

TOOLSETS = {"records": RECORDS_TOOLS, "graph": GRAPH_TOOLS}


def run(toolset: str, name: str, args: dict, ctx: Context) -> tuple[dict, str, bool]:
    """Run one tool. Returns (result, step title, is_error). Errors come back as results."""
    tool = next((t for t in TOOLSETS[toolset] if t.name == name), None)
    if tool is None:
        return {"error": f"Unknown tool {name}."}, f"unknown tool {name}", True
    try:
        result = tool.handler(ctx, **(args or {}))
        return result, tool.step_title(args or {}, result), False
    except (ValueError, OntologyError, RecordsError, TypeError) as e:
        return {"error": str(e)}, f"{name} failed: {e}", True
