"""The ordinary store: SQLite tables with keyword search, like most teams' setups.

One table per record type, holding the fields a normal system would hold. No joins and no
SQL for callers: just search, get one record, and simple filtered listing. The tables hold
the base fields only and are not affected by ontology changes.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from wander.stores import filters

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "records.db"

# record type -> columns (besides id). These are the only fields the records store knows.
TABLES: dict[str, list[str]] = {
    "customers": ["name", "status", "plan", "churn_reason", "churned_at", "plan_change",
                  "plan_changed_at", "payment_status", "refund_requested_at", "account_manager"],
    "tickets": ["customer_id", "customer_name", "title", "topic", "status", "queue", "feature",
                "created_at"],
    "documents": ["title", "type", "text", "comments"],
    "people": ["name", "role", "team"],
    "decisions": ["title", "date", "summary"],
}

# which columns feed the keyword index
SEARCH_TITLE = {"customers": "name", "tickets": "title", "documents": "title", "people": "name",
                "decisions": "title"}


class RecordsError(ValueError):
    pass


class RecordsStore:
    def __init__(self, path: Path | str | None = None):
        path = Path(path or DB_PATH)
        if not path.exists():
            raise RecordsError(f"No records database at {path}. Run: uv run python -m wander.cli load")
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self.db.row_factory = sqlite3.Row

    def search(self, query: str, type: str | None = None, limit: int = 10) -> list[dict]:
        """Keyword search across every record type. Any of the words may match; best first."""
        words = re.findall(r"\w+", query or "")
        if not words:
            return []
        if type is not None and type not in TABLES:
            raise RecordsError(f"Unknown record type {type}. Use one of {', '.join(TABLES)}.")
        fts = " OR ".join(f'"{w}"' for w in words)
        sql = "SELECT id, type, title, snippet(search, 3, '[', ']', '…', 12) AS snippet FROM search WHERE search MATCH ?"
        params: list = [fts]
        if type:
            sql += " AND type = ?"
            params.append(type)
        sql += " ORDER BY bm25(search) LIMIT ?"
        params.append(max(1, min(int(limit), 50)))
        return [dict(r) for r in self.db.execute(sql, params)]

    def get_record(self, record_id: str) -> dict | None:
        for table in TABLES:
            row = self.db.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
            if row:
                return {"type": table, **{k: v for k, v in dict(row).items() if v is not None}}
        return None

    def list_records(self, type: str, filters_: dict | None = None, limit: int = 25) -> dict:
        if type not in TABLES:
            raise RecordsError(f"Unknown record type {type}. Use one of {', '.join(TABLES)}.")
        where = filters.validate(filters_)
        unknown = set(where) - set(TABLES[type]) - {"id"}
        if unknown:
            raise RecordsError(f"{type} has no field(s) {', '.join(sorted(unknown))}. "
                               f"Fields: {', '.join(['id'] + TABLES[type])}.")
        rows = [dict(r) for r in self.db.execute(f"SELECT * FROM {type} ORDER BY id")]
        hits = [{k: v for k, v in r.items() if v is not None} for r in rows if filters.matches(r, where)]
        limit = max(1, min(int(limit), 100))
        return {"type": type, "total": len(hits), "returned": min(len(hits), limit), "records": hits[:limit]}

    def counts(self) -> dict[str, int]:
        return {t: self.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
