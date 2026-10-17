"""Command line: the raw context Claude would receive, with no LLM involved.

    uv run python -m wander.cli --help
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from wander import core, proposals, tools
from wander import ontology as onto_mod
from wander.render import render

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "data" / "generated" / "scenarios.json"

app = typer.Typer(help="Teaching software to wander: the graph and the records store, without an LLM.",
                  no_args_is_help=True, add_completion=False)
records_app = typer.Typer(help="What the Records agent sees.", no_args_is_help=True)
ontology_app = typer.Typer(help="View and change the ontology.", no_args_is_help=True)
app.add_typer(records_app, name="records")
app.add_typer(ontology_app, name="ontology")

StoreOpt = typer.Option("neo4j", "--store", help="neo4j, or memory to run without Docker.")
FormatOpt = typer.Option("text", "--format", help="text (readable) or json (everything).")


def _out(tool: str, result: dict, fmt: str) -> None:
    if fmt == "json":
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        typer.echo(render(tool, result))
    if "error" in result:
        raise typer.Exit(1)


def _run(toolset: str, tool: str, args: dict, store: str, fmt: str = "text") -> dict:
    result, _, _ = tools.run(toolset, tool, args, tools.Context(store))
    _out(tool, result, fmt)
    return result


def _scenarios() -> list[dict]:
    return json.loads(SCENARIOS.read_text())


@app.command()
def load(store: str = StoreOpt, regenerate: bool = typer.Option(False, help="Rebuild the JSON first.")):
    """Generate the data (if needed), then load the records store and the graph."""
    from data import load_records

    if regenerate or not (ROOT / "data" / "generated" / "nodes.json").exists():
        from data import generate
        generate.main()
    counts = load_records.load()
    typer.echo("Records: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    if store == "neo4j":
        from data import load_graph
        c = load_graph.load()
        typer.echo(f"Graph: {c['nodes']} nodes, {c['edges']} relationships loaded into Neo4j "
                   "(only what the ontology declares).")
    else:
        typer.echo("Graph: using the in-memory store, nothing to load.")


@app.command()
def scenarios():
    """List the scenarios and their questions."""
    for s in _scenarios():
        typer.echo(f"{s['name']:<22} {s['title']}\n{'':<22} “{s['question']}”")


@app.command()
def wander(
    scenario: Optional[str] = typer.Option(None, help="Use a scenario's anchors (see `scenarios`)."),
    churned_since: Optional[str] = typer.Option(None, help="Customers who churned on or after this date."),
    anchors: Optional[str] = typer.Option(None, help="Comma-separated node ids."),
    max_hops: int = typer.Option(5),
    min_support: float = typer.Option(0.6),
    min_lift: float = typer.Option(2.0),
    prune: bool = typer.Option(True, "--prune/--no-prune"),
    store: str = StoreOpt,
    format: str = FormatOpt,
):
    """Wander from some starting points and print what the graph hands Claude."""
    ctx = tools.Context(store)
    if anchors:
        ids = [a.strip() for a in anchors.split(",") if a.strip()]
    else:
        if scenario:
            match = [s for s in _scenarios() if s["name"] == scenario]
            if not match:
                raise typer.BadParameter(f"No scenario {scenario}. Try: " +
                                         ", ".join(s["name"] for s in _scenarios()))
            sel = match[0]["anchors"]
            type_, where = sel["type"], sel.get("where")
        elif churned_since:
            type_, where = "Customer", {"churned_at": {"gte": churned_since}}
        else:
            raise typer.BadParameter("Give --scenario, --churned-since or --anchors.")
        found, _, err = tools.run("graph", "find", {"type": type_, "filters": where, "limit": 200}, ctx)
        if err:
            _out("find", found, format)
        ids = [n["id"] for n in found["nodes"]]
    # The CLI exposes the guardrail knobs; the tool Claude calls always uses the defaults.
    try:
        result = core.wander(ctx.graph, ids, max_hops=max_hops, min_support=min_support,
                             min_lift=min_lift, prune=prune)
    except ValueError as e:
        result = {"error": str(e)}
    _out("wander", result, format)


@app.command("base-rate")
def base_rate(node: str, since: Optional[str] = typer.Option(None), outcome: str = typer.Option("churned"),
              pattern: Optional[str] = typer.Option(None), store: str = StoreOpt, format: str = FormatOpt):
    """Compare an outcome's rate with and without a connection to NODE."""
    _run("graph", "compare_base_rate", {"node": node, "since": since, "outcome": outcome, "pattern": pattern},
         store, format)


@app.command()
def details(node: str, store: str = StoreOpt, format: str = FormatOpt):
    """One node in full, with its immediate connections."""
    _run("graph", "get_details", {"node": node}, store, format)


@app.command()
def find(type: Optional[str] = typer.Argument(None), name: Optional[str] = typer.Option(None),
         where: Optional[str] = typer.Option(None, help='Filters as JSON, e.g. \'{"status": "churned"}\'.'),
         store: str = StoreOpt, format: str = FormatOpt):
    """Look nodes up in the graph."""
    _run("graph", "find", {"type": type, "name": name, "filters": json.loads(where) if where else None},
         store, format)


@records_app.command("search")
def records_search(query: str, type: Optional[str] = typer.Option(None), limit: int = 10,
                   format: str = FormatOpt):
    """Keyword search, as the Records agent would run it."""
    _run("records", "search", {"query": query, "type": type, "limit": limit}, "memory", format)


DATE_FIELDS = {"customers": "churned_at", "tickets": "created_at", "decisions": "date"}


@records_app.command("list")
def records_list(type: str, status: Optional[str] = typer.Option(None),
                 since: Optional[str] = typer.Option(None, help="On or after, on the type's main date field."),
                 where: Optional[str] = typer.Option(None, help="Extra filters as JSON."),
                 limit: int = 25, format: str = FormatOpt):
    """Filtered listing, as the Records agent would run it."""
    filters = json.loads(where) if where else {}
    if status:
        filters["status"] = status
    if since:
        filters[DATE_FIELDS.get(type, "created_at")] = {"gte": since}
    _run("records", "list_records", {"type": type, "filters": filters, "limit": limit}, "memory", format)


@records_app.command("get")
def records_get(id: str, format: str = FormatOpt):
    """One record's own fields."""
    _run("records", "get_record", {"id": id}, "memory", format)


@ontology_app.command("show")
def ontology_show():
    """The current ontology, in plain language."""
    typer.echo(onto_mod.Ontology.load().describe())


@ontology_app.command("propose")
def ontology_propose(
    kind: str = typer.Argument(..., help="entity, property or relationship"),
    name: str = typer.Argument(...),
    description: str = typer.Option(..., "--description", "-d"),
    by: str = typer.Option(..., "--by", help="Who is proposing it."),
    entity: Optional[str] = typer.Option(None, help="For a property: which entity or relationship."),
    from_: Optional[str] = typer.Option(None, "--from", help="For a relationship: from which entity."),
    to: Optional[str] = typer.Option(None, help="For a relationship: to which entity."),
    properties: Optional[str] = typer.Option(None, help='As JSON, e.g. \'{"notes": "Anything to know."}\'.'),
):
    """Propose an entity, property or relationship. It waits for review; nothing changes yet."""
    change = {"kind": kind, "name": name, "description": description, "proposed_by": by, "entity": entity,
              "from": from_, "to": to, "properties": json.loads(properties) if properties else None}
    _change(lambda: proposals.propose(change))


@ontology_app.command("pending")
def ontology_pending():
    """The proposals waiting for review, and what each would load."""
    state = proposals.pending()
    if not state["pending"]:
        typer.echo("No proposals waiting for review.")
    for p in state["pending"]:
        status = (f"would load {p['would_load']} {p['unit']}" if p["valid"] and p["would_load"]
                  else "no data yet" if p["valid"] else f"PROBLEM: {p['problem']}")
        typer.echo(f"{p['id']}  {p['summary']}\n      proposed by {p['proposed_by']} on {p['proposed_at']} · {status}")


@ontology_app.command("apply")
def ontology_apply(ids: Optional[list[str]] = typer.Argument(None, help="Proposal ids, e.g. p1 p2."),
                   all_: bool = typer.Option(False, "--all", help="Apply every valid pending proposal."),
                   by: str = typer.Option(..., "--by", help="Who reviewed them."),
                   store: str = StoreOpt):
    """Apply reviewed proposals to the live ontology, and reload the graph once."""
    if all_:
        ids = [p["id"] for p in proposals.pending()["pending"] if p["valid"]]
    if not ids:
        raise typer.BadParameter("Give proposal ids, or --all.")
    result = _change(lambda: proposals.apply(tools.Context(store), ids, by))
    for r in result["applied"]:
        typer.echo(f"  {r['id']}: loaded {r['loaded']} {r['unit']}")


@ontology_app.command("reject")
def ontology_reject(pid: str, by: str = typer.Option(..., "--by", help="Who reviewed it."),
                    reason: str = typer.Option("", "--reason")):
    """Reject a proposal. It's kept, with the reason, for the record."""
    _change(lambda: proposals.reject(pid, by, reason))


def _change(fn) -> dict:
    try:
        result = fn()
    except (onto_mod.OntologyError, ValueError) as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)
    typer.echo(result["message"])
    return result


@ontology_app.command("reset")
def ontology_reset(store: str = StoreOpt):
    """Restore ontology.initial.yaml (dropping pending proposals) and reload, so the demo can run again."""
    onto = onto_mod.reset()
    if store == "neo4j":
        from data import load_graph
        load_graph.load(onto)
    typer.echo(f"Ontology reset to {onto_mod.INITIAL_PATH.name}: {len(onto.entities)} entities, "
               f"{len(onto.relationships)} relationships.")


@app.command()
def viewer(port: int = 8765):
    """Serve the ontology viewer on localhost, reading ontology.yaml live."""
    from wander.viewer.server import serve
    serve(port)


if __name__ == "__main__":
    app()
