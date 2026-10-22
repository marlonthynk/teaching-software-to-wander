"""Check a scenario's expected outcome against the real wander, on Neo4j.

Used by tests/test_scenarios.py. Expected-outcome keys, all optional except anchor_count
and convergence:

    anchor_count           how many nodes the anchor selector picks
    before_ontology        {"convergence": ...} expected before ontology_additions are applied
    ontology_additions     changes to apply (as a developer would) before the main check
    convergence            {"type", "name"} of the top kept node, or None for "nothing found"
    lift_range             [low, high] for the top kept node's lift
    explanation_includes   names that must appear in its explanation
    other_members_include  ids that must be among its other members
    other_members_exact    ids that must be exactly its other members
    pruned_include         [{"name"|"type", "reason", "lift_range"?}] that must be among the pruned
    base_rate              {"node", "since", "outcome", "with": [k, n], "without": [k, n]}
"""

from __future__ import annotations

from wander.graph.db import Graph
from wander.graph.lookups import find
from wander.graph.wander import compare_base_rate, wander
from wander.ontology import INITIAL_PATH, Ontology


def check(scenario: dict, graph: Graph) -> list[str]:
    """Run one scenario's question through the wander and compare with what it should find.
    If the scenario needs ontology additions, they're loaded into Neo4j for the check, and the
    graph is reloaded with the original ontology afterwards."""
    exp = scenario["expected"]
    name = scenario["name"]
    original = graph.ontology
    failures: list[str] = []
    try:
        if "before_ontology" in exp:
            failures += _check_convergence(name + " (before ontology change)", _run(graph, scenario),
                                           {"convergence": exp["before_ontology"]["convergence"]})
        if exp.get("ontology_additions"):
            onto = original.copy()
            for change in exp["ontology_additions"]:
                onto.apply(change)
            graph.reload(onto)
        result = _run(graph, scenario)
        if len(result["anchors"]) != exp["anchor_count"]:
            failures.append(f"{name}: expected {exp['anchor_count']} anchors, got {len(result['anchors'])}")
        failures += _check_convergence(name, result, exp)
        failures += _check_pruned(name, result, exp.get("pruned_include", []))
        if "base_rate" in exp:
            failures += _check_base_rate(name, graph, exp["base_rate"])
    finally:
        if exp.get("ontology_additions"):
            graph.reload(original)
    return failures


def _run(graph, scenario) -> dict:
    sel = scenario["anchors"]
    anchors = [n["id"] for n in find(graph, sel["type"], sel.get("where"), limit=200)["nodes"]]
    return wander(graph, anchors)


def _check_convergence(name, result, exp) -> list[str]:
    kept = result["convergence"]
    want = exp["convergence"]
    if want is None:
        return [f"{name}: expected no common thread, but kept " +
                ", ".join(f"{c['type']} {c['name']}" for c in kept)] if kept else []
    if not kept:
        return [f"{name}: expected {want['type']} {want['name']}, but nothing was kept"]
    top = kept[0]
    out = []
    if (top["type"], top["name"]) != (want["type"], want["name"]):
        out.append(f"{name}: expected {want['type']} {want['name']} first, got {top['type']} {top['name']}")
    lo, hi = exp.get("lift_range", [0, float("inf")])
    if not lo <= top["lift"] <= hi:
        out.append(f"{name}: lift {top['lift']} outside {lo}-{hi}")
    text = " ".join(e["path"] for e in top["explanation"])
    for needed in exp.get("explanation_includes", []):
        if needed not in text:
            out.append(f"{name}: explanation doesn't reach {needed}")
    members = {m["id"] for m in top["other_members"]["members"]}
    if "other_members_include" in exp and not set(exp["other_members_include"]) <= members:
        out.append(f"{name}: other members miss {sorted(set(exp['other_members_include']) - members)}")
    if "other_members_exact" in exp and members != set(exp["other_members_exact"]):
        out.append(f"{name}: other members are {sorted(members)}, expected {sorted(exp['other_members_exact'])}")
    return out


def _check_pruned(name, result, wanted) -> list[str]:
    out = []
    for w in wanted:
        hits = [p for p in result["pruned"] if p["reason"] == w["reason"]
                and w.get("name", p["name"]) == p["name"] and w.get("type", p["type"]) == p["type"]]
        lo, hi = w.get("lift_range", [0, float("inf")])
        if not any(lo <= p["lift"] <= hi for p in hits):
            out.append(f"{name}: expected a pruned {w.get('name') or w.get('type')} ({w['reason']})")
    return out


def _check_base_rate(name, graph, exp) -> list[str]:
    r = compare_base_rate(graph, exp["node"], since=exp.get("since"), outcome=exp["outcome"])
    got = ([r["with"]["outcome"], r["with"]["count"]], [r["without"]["outcome"], r["without"]["count"]])
    if got != (exp["with"], exp["without"]):
        return [f"{name}: base rate {got}, expected {exp['with']} vs {exp['without']}"]
    return []


def check_all(scenarios: list[dict]) -> list[str]:
    """Every scenario, on Neo4j loaded through the initial ontology."""
    graph = Graph(Ontology.load(INITIAL_PATH))
    graph.reload(graph.ontology)
    try:
        return [f for s in scenarios for f in check(s, graph)]
    finally:
        graph.close()
