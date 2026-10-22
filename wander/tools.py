"""Both toolsets, side by side, and what they run against. Used unchanged by the chat app, the
MCP servers and the CLI.

    records: wander/records/tools.py — search, get a record, list records (SQLite)
    graph:   wander/graph/tools.py   — wander, compare_base_rate, get_details, find, view_ontology (Neo4j)

Neither toolset can change the ontology: that happens in the viewer (proposals) and on its
Review page (a developer applies them). See wander/proposals.py.
"""

from __future__ import annotations

from wander.graph import tools as graph_tools
from wander.graph.db import Graph
from wander.ontology import Ontology, OntologyError, ontology_path
from wander.records import tools as records_tools
from wander.records.store import RecordsError, RecordsStore

TOOLSETS = {"records": records_tools.TOOLS, "graph": graph_tools.TOOLS}


class Context:
    """The two stores. Each opens when first used, so a Records-only chat never needs Neo4j."""

    def __init__(self, records_path=None):
        self.records_path = records_path
        self._graph: Graph | None = None
        self._records: RecordsStore | None = None
        self._ontology_version: int | None = None

    @property
    def graph(self) -> Graph:
        """Neo4j, with the ontology kept up to date: a developer may apply changes from the viewer
        while this process is running, so each use checks whether ontology.yaml changed."""
        version = ontology_path().stat().st_mtime_ns
        if self._graph is None:
            self._graph = Graph(Ontology.load())
        elif version != self._ontology_version:
            self._graph.ontology = Ontology.load()
        self._ontology_version = version
        return self._graph

    @property
    def records(self) -> RecordsStore:
        if self._records is None:
            self._records = RecordsStore(self.records_path)
        return self._records


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
