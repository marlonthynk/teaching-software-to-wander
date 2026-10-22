"""The Graph agent's tools. The wander does the walking and pruning on the server; Claude only
says where to start.

None of these change the ontology: people propose that in the viewer, and a developer
applies it (wander/proposals.py).
"""

from __future__ import annotations

import json

from wander.graph.lookups import find, get_details
from wander.graph.wander import compare_base_rate, wander
from wander.ontology import Ontology
from wander.toolkit import FILTERS_HELP, Tool, schema


def _wander(ctx, anchors: list[str]) -> dict:
    # Hops, support and lift stay at the server's defaults: the guardrails aren't Claude's to
    # loosen, and the same starting points always give the same context. The CLI has the knobs.
    return wander(ctx.graph, anchors)


def _wander_title(a: dict, r: dict) -> str:
    s = r.get("stats", {})
    kind = (r.get("anchors") or [{}])[0].get("type", "node").lower()
    n = len(r.get("anchors", []))
    return (f"wander from {n} {kind}{'s' if n != 1 else ''} ({len(r.get('convergence', []))} found, "
            f"{len(r.get('pruned', []))} pruned, {s.get('nodes_returned', 0)} nodes returned)")


def _base_rate(ctx, node: str, since: str | None = None, outcome: str = "churned") -> dict:
    return compare_base_rate(ctx.graph, node, since=since, outcome=outcome)


def _details(ctx, node: str) -> dict:
    return get_details(ctx.graph, node)


def _find(ctx, type: str | None = None, filters: dict | None = None, name: str | None = None,
          limit: int = 50) -> dict:
    return find(ctx.graph, type, filters, name, limit)


def _view_ontology(ctx) -> dict:
    return {"ontology": Ontology.load().describe()}


TOOLS = [
    Tool(
        "wander",
        "Start from one or more things of the same kind (e.g. customers) and walk outwards through "
        "everything they are connected to, following every relationship the ontology declares. "
        "The tool does the walking and the pruning: it returns the things the starting points "
        "converge on more than chance would explain, the paths that lead there, what lies behind "
        "each one, who else shares the same thread, and what it pruned and why. Use find first "
        "to get the starting ids.",
        schema({"anchors": {"type": "array", "items": {"type": "string"}, "description": "Starting node ids."}},
               ["anchors"]),
        _wander,
        _wander_title,
    ),
    Tool(
        "compare_base_rate",
        "Compare how often an outcome happens for things connected to a node versus everything "
        "else, e.g. the churn rate of customers connected to X against all other customers. "
        "Optionally count only connections dated on or after a date. A signal, not proof.",
        schema({"node": {"type": "string", "description": "Node id or name."},
                "since": {"type": "string", "description": "Only connections dated on or after this date (YYYY-MM-DD)."},
                "outcome": {"type": "string",
                            "description": "The outcome to count: a status value such as 'churned', or field=value."}},
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
        schema({"node": {"type": "string", "description": "Node id or name."}}, ["node"]),
        _details,
        lambda a, r: f"details of {r.get('type', '')} {r.get('name', a.get('node'))}",
    ),
    Tool(
        "find",
        "Look up nodes by type, by filters on their properties, or by name. " + FILTERS_HELP,
        schema({"type": {"type": "string", "description": "Entity type, e.g. Customer. See view_ontology."},
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
        schema({}),
        _view_ontology,
        lambda a, r: "view ontology",
    ),
]
