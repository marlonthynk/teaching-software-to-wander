"""The Records agent's tools: what most teams have — search, open a record, list with filters.

No joins and no way to follow a connection: each record is read on its own.
"""

from __future__ import annotations

import json

from wander.records.store import TABLES, RecordsError
from wander.toolkit import FILTERS_HELP, Tool, schema


def _search(ctx, query: str, type: str | None = None, limit: int = 10) -> dict:
    return {"query": query, "results": ctx.records.search(query, type, limit)}


def _get_record(ctx, id: str) -> dict:
    record = ctx.records.get_record(id)
    if record is None:
        raise RecordsError(f"No record with id {id}.")
    return record


def _list_records(ctx, type: str, filters: dict | None = None, limit: int = 25) -> dict:
    return ctx.records.list_records(type, filters, limit)


RECORD_FIELDS = "; ".join(f"{t}: {', '.join(['id'] + cols)}" for t, cols in TABLES.items())

TOOLS = [
    Tool(
        "search",
        "Keyword search across the company's records: customers (CRM), support tickets, documents "
        "(including comments on them), people and decisions. Any of the words may match; best "
        "matches first. Returns ids and short snippets; use get_record for the full record.",
        schema({"query": {"type": "string", "description": "Words to search for."},
                "type": {"type": "string", "enum": list(TABLES), "description": "Only this record type."},
                "limit": {"type": "integer", "description": "At most this many results (default 10, max 50)."}},
               ["query"]),
        _search,
        lambda a, r: f"search “{a.get('query')}” ({len(r.get('results', []))} results)",
    ),
    Tool(
        "get_record",
        "Get one record's own fields by id.",
        schema({"id": {"type": "string", "description": "The record id, e.g. cust_014 or tkt_0042."}}, ["id"]),
        _get_record,
        lambda a, r: f"get record {a.get('id')}",
    ),
    Tool(
        "list_records",
        "List records of one type, optionally filtered on their own fields. " + FILTERS_HELP +
        f" Fields by type — {RECORD_FIELDS}.",
        schema({"type": {"type": "string", "enum": list(TABLES)},
                "filters": {"type": "object", "description": FILTERS_HELP},
                "limit": {"type": "integer", "description": "At most this many records (default 25, max 100)."}},
               ["type"]),
        _list_records,
        lambda a, r: f"list {a.get('type')} {json.dumps(a.get('filters') or {})} ({r.get('total', 0)} found)",
    ),
]
