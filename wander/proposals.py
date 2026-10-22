"""Proposing, reviewing and applying ontology changes, with the graph in step.

Anyone in the organisation can propose a change (from the viewer, or the CLI). Proposals
are validated and staged in ontology.yaml; the graph doesn't change. A developer reviews
them and applies the ones they approve: only then is the live ontology updated and the
graph reloaded, once, for the whole batch.

The chat can't change the ontology: its agents only read it (view_ontology).
"""

from __future__ import annotations

from wander.ontology import Ontology
from data.source import read_generated, visible_data

UNITS = {"entity": "nodes", "relationship": "relationships", "property": "values"}


def propose(change: dict) -> dict:
    """Validate and stage one change. Says how much data it would bring in, once applied."""
    onto = Ontology.load()
    proposal = onto.propose(change)
    onto.save()
    would = loaded_for(onto.with_pending(), proposal)
    summary = proposal["summary"].rstrip(".")
    if would:
        message = (f"Proposed {proposal['id']}: {summary}. It's waiting for a developer to review "
                   f"and apply it; once applied, {would} {UNITS[proposal['kind']]} will load.")
    else:
        message = (f"Proposed {proposal['id']}: {summary}. It's waiting for a developer to review "
                   "it. No data found for it yet, so someone would also need to supply that.")
    return {"proposal": proposal["id"], "status": "pending review", "would_load": would, "message": message}


def pending() -> dict:
    """The review list: each pending proposal, whether it's valid, and what it would load."""
    onto = Ontology.load()
    trial = onto.copy()
    items = []
    for p in onto.review():
        if p["valid"]:
            trial.apply(p)
        items.append({**p, "would_load": loaded_for(trial, p) if p["valid"] else 0,
                      "unit": UNITS[p["kind"]]})
    return {"pending": items, "rejected": onto.rejected[-10:][::-1],
            "recently_applied": [c for c in onto.changelog if c.get("reviewed_by")][-10:][::-1]}


def apply(ctx, ids: list[str], reviewed_by: str) -> dict:
    """Apply the approved proposals, then reload the graph once for all of them."""
    onto = Ontology.load()
    applied = onto.apply_proposals(ids, reviewed_by)
    onto.save()
    ctx.graph.reload(onto)
    results = [{"id": p["id"], "summary": p["summary"], "loaded": loaded_for(onto, p),
                "unit": UNITS[p["kind"]]} for p in applied]
    return {"applied": results,
            "message": f"Applied {len(results)} change{'s' if len(results) != 1 else ''} and reloaded the graph."}


def reject(pid: str, reviewed_by: str, reason: str = "") -> dict:
    onto = Ontology.load()
    record = onto.reject(pid, reviewed_by, reason)
    onto.save()
    return {"rejected": record["id"], "message": f"Rejected {record['id']} ({record['name']})."}


def loaded_for(onto: Ontology, change: dict) -> int:
    """How much existing data a change brings into the graph, given an ontology that includes it."""
    nodes, edges = visible_data(onto, *read_generated())
    if change["kind"] == "entity":
        return sum(1 for n in nodes if n["type"] == change["name"])
    if change["kind"] == "relationship":
        return sum(1 for e in edges if e["type"] == change["name"])
    target, prop = change["entity"], change["name"]
    if target in onto.relationships:
        return sum(1 for e in edges if e["type"] == target and prop in e["properties"])
    return sum(1 for n in nodes if n["type"] == target and prop in n["properties"])
