"""Build the records store (data/records.db) from the same generated JSON as the graph.

    uv run python -m data.load_records

The records store holds the base fields only: what the initial ontology declares, laid out
the way an ordinary CRM, ticketing system and wiki would hold it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from wander.ontology import INITIAL_PATH, Ontology
from wander.stores.graph import read_generated, visible_data
from wander.stores.records import DB_PATH, SEARCH_TITLE, TABLES


def load(path: Path = DB_PATH) -> dict[str, int]:
    # Same data, seen through the initial ontology only: no partners, renewals, escalations.
    nodes, edges = visible_data(Ontology.load(INITIAL_PATH), *read_generated())
    by_id = {n["id"]: n for n in nodes}

    def name(node_id):
        return by_id[node_id]["properties"].get("name")

    manager = {e["to"]: name(e["from"]) for e in edges if e["type"] == "MANAGES"}
    raised_by = {e["to"]: e["from"] for e in edges if e["type"] == "RAISED"}
    queue = {e["from"]: name(e["to"]) for e in edges if e["type"] == "ROUTED_TO"}
    feature = {e["from"]: name(e["to"]) for e in edges if e["type"] == "ABOUT"}
    comments: dict[str, list[str]] = {}
    for e in sorted((e for e in edges if e["type"] == "COMMENTED_ON"), key=lambda e: e["properties"]["date"]):
        comments.setdefault(e["to"], []).append(
            f"{name(e['from'])} ({e['properties']['date']}): {e['properties']['text']}")

    rows: dict[str, list[dict]] = {t: [] for t in TABLES}
    for n in nodes:
        p, i = n["properties"], n["id"]
        if n["type"] == "Customer":
            rows["customers"].append({"id": i, **p, "account_manager": manager.get(i)})
        elif n["type"] == "Ticket":
            cust = raised_by[i]
            rows["tickets"].append({"id": i, **p, "customer_id": cust, "customer_name": name(cust),
                                    "queue": queue.get(i), "feature": feature.get(i)})
        elif n["type"] == "Document":
            rows["documents"].append({"id": i, **p, "comments": "\n".join(comments.get(i, [])) or None})
        elif n["type"] == "Person":
            rows["people"].append({"id": i, **p})
        elif n["type"] == "Decision":
            rows["decisions"].append({"id": i, **p})

    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    with db:
        db.execute("CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, type UNINDEXED, title, body)")
        for table, columns in TABLES.items():
            db.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, {', '.join(c + ' TEXT' for c in columns)})")
            for r in rows[table]:
                values = [r["id"]] + [r.get(c) for c in columns]
                db.execute(f"INSERT INTO {table} VALUES ({', '.join('?' * len(values))})", values)
                title = r.get(SEARCH_TITLE[table]) or ""
                body = " ".join(str(r[c]) for c in columns if r.get(c) and c != SEARCH_TITLE[table])
                db.execute("INSERT INTO search VALUES (?, ?, ?, ?)", (r["id"], table, title, body))
    db.close()
    return {t: len(r) for t, r in rows.items()}


if __name__ == "__main__":
    counts = load()
    print("Loaded records:", ", ".join(f"{v} {k}" for k, v in counts.items()), f"into {DB_PATH}")
