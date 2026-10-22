"""What a tool is. Each store defines its own (wander/graph/tools.py, wander/records/tools.py);
wander/tools.py puts them together for the chat app, the MCP servers and the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str          # what Claude reads to decide when to use it
    input_schema: dict        # what Claude must pass
    handler: Callable[..., dict]
    step_title: Callable[[dict, dict], str]   # the one-line title of the step in the chat app

    def api_spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


FILTERS_HELP = ('Filters on the record\'s own fields: {"field": value} for equality, or '
                '{"field": {"gte": ..., "lte": ...}} for a range (dates are YYYY-MM-DD).')
