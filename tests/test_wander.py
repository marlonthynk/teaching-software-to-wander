"""The article's scenario, on Neo4j: the wander finds the dead queue and prunes the noise."""

import pytest

from wander.graph import tools as graph_tools
from wander.graph.lookups import get_details
from wander.graph.wander import compare_base_rate, wander


@pytest.fixture(scope="module")
def result(graph):
    from wander.graph.lookups import find
    anchors = [n["id"] for n in find(graph, "Customer",
                                     {"churned_at": {"gte": "2026-07-01", "lte": "2026-09-30"}})["nodes"]]
    return wander(graph, anchors)


def test_finds_the_integrations_queue(result):
    assert len(result["convergence"]) == 1
    top = result["convergence"][0]
    assert (top["type"], top["name"]) == ("Queue", "Integrations")
    assert top["support"] == "5 of 5" and top["population_reach"] == "27 of 67"
    assert 2.4 <= top["lift"] <= 2.5
    assert len(top["paths"]) == 5 and all("Queue(Integrations" in p for p in top["paths"])


def test_explanation_reaches_daniela(result):
    text = " ".join(e["path"] for e in result["convergence"][0]["explanation"])
    for needed in ("Decision(Support reorg", "Document(Reorg plan", "Person(Daniela", "routing rule"):
        assert needed in text


def test_whats_behind_the_queue_is_explanation_not_findings(result):
    names = {c["name"] for c in result["convergence"]} | {p["name"] for p in result["pruned"]}
    assert not names & {"Support reorg", "Reorg plan: support teams 2026", "Daniela", "Rosa"}


def test_who_else_includes_the_twelve_at_risk(result):
    members = result["convergence"][0]["other_members"]
    assert members["count"] == 22
    assert members["breakdown"]["Ticket.status"] == {"open": 12, "closed": 10}


def test_prunes_hubs_features_and_account_managers_with_reasons(result):
    pruned = {p["name"]: p for p in result["pruned"]}
    assert pruned["General support"]["reason"] == "hub"
    assert any(p["type"] == "Feature" and p["reason"] == "low support" for p in result["pruned"])
    assert any(p["type"] == "Person" and p["reason"] == "low support" for p in result["pruned"])
    assert all(p["why"] for p in result["pruned"])


def test_base_rate(graph):
    r = compare_base_rate(graph, "Integrations", since="2026-03-15")
    assert (r["with"]["outcome"], r["with"]["count"]) == (5, 17)
    assert (r["without"]["outcome"], r["without"]["count"]) == (2, 50)
    assert "29%" in r["summary"] and "4%" in r["summary"] and "not proof" in r["summary"]


def test_is_deterministic(graph, q3_churners, result):
    assert wander(graph, q3_churners) == result


def test_without_guardrails_the_context_explodes(graph, q3_churners, result):
    unpruned = wander(graph, q3_churners, max_hops=6, prune=False)
    assert unpruned["stats"]["approx_tokens"] > 10 * result["stats"]["approx_tokens"]


def test_one_hop_is_not_enough(graph, q3_churners):
    assert wander(graph, q3_churners, max_hops=1)["convergence"] == []


def test_get_details_shows_comments(graph):
    d = get_details(graph, "Daniela")
    assert d["type"] == "Person" and any("routing rule" in e.get("text", "") for e in d["edges"])


def test_rejects_mixed_or_unknown_starting_points(graph):
    with pytest.raises(ValueError):
        wander(graph, ["cust_001", "queue_general"])
    with pytest.raises(ValueError):
        wander(graph, ["nope"])


def test_claude_cannot_loosen_the_guardrails():
    spec = next(t for t in graph_tools.TOOLS if t.name == "wander").input_schema
    assert set(spec["properties"]) == {"anchors"}
