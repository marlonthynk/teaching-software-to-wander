"""Convergence finds the queue, and the guardrails prune the noise."""

import pytest

from wander import core


@pytest.fixture
def result(store, q3_churners):
    return core.wander(store, q3_churners)


def test_finds_the_integrations_queue_first(result):
    top = result["convergence"][0]
    assert (top["type"], top["name"]) == ("Queue", "Integrations")
    assert top["support"] == "5 of 5"
    assert 2.2 <= top["lift"] <= 2.8
    assert len(top["paths"]) == 5 and all("Queue(Integrations" in p for p in top["paths"])


def test_explanation_reaches_daniela(result):
    text = " ".join(e["path"] for e in result["convergence"][0]["explanation"])
    for needed in ("Decision(Support reorg", "Document(Reorg plan", "Person(Daniela", "routing rule"):
        assert needed in text


def test_things_behind_the_queue_are_explanation_not_findings(result):
    kept = {c["name"] for c in result["convergence"]}
    pruned = {p["name"] for p in result["pruned"]}
    for name in ("Support reorg", "Reorg plan: support teams 2026", "Daniela"):
        assert name not in kept and name not in pruned


def test_other_members_include_the_twelve_at_risk(store, result):
    members = result["convergence"][0]["other_members"]["members"]
    at_risk = []
    for m in members:
        open_after = [s for t in m["through"] for s in t["via"]
                      if s["status"] == "open" and s["created_at"] >= "2026-03-15"]
        if m["status"] == "active" and open_after:
            at_risk.append(m["id"])
    assert len(at_risk) == 12


def test_prunes_hubs_features_and_account_managers_with_reasons(result):
    pruned = {p["name"]: p for p in result["pruned"]}
    assert pruned["General support"]["reason"] == "hub"
    assert any(p["type"] == "Feature" and p["reason"] == "low support" for p in result["pruned"])
    assert any(p["type"] == "Person" and p["reason"] == "low support" for p in result["pruned"])
    assert all(p["why"] for p in result["pruned"])


def test_pruned_list_only_holds_nodes_shared_by_two_or_more(result):
    for p in result["pruned"]:
        assert int(p["support"].split(" of ")[0]) >= 2


def test_hubs_are_listed_once_and_not_expanded(result):
    names = [p["name"] for p in result["pruned"]]
    assert names.count("General support") == 1
    assert result["stats"]["hubs_not_expanded"] >= 1


def test_is_deterministic(store, q3_churners):
    assert core.wander(store, q3_churners) == core.wander(store, q3_churners)


def test_no_prune_returns_far_more(store, q3_churners, result):
    unpruned = core.wander(store, q3_churners, max_hops=6, prune=False)
    assert unpruned["stats"]["nodes_returned"] > 5 * result["stats"]["nodes_returned"]
    assert unpruned["stats"]["approx_tokens"] > 10 * result["stats"]["approx_tokens"]


def test_one_hop_is_not_enough(store, q3_churners):
    assert core.wander(store, q3_churners, max_hops=1)["convergence"] == []


def test_node_budget_is_visible(store, q3_churners):
    r = core.wander(store, q3_churners, max_nodes=50)
    assert r["stats"]["truncated"] is True
    assert r["stats"]["nodes_visited"] <= 50


def test_base_rate(store):
    r = core.compare_base_rate(store, "Integrations", since="2026-03-15")
    assert (r["with"]["outcome"], r["with"]["count"]) == (5, 17)
    assert (r["without"]["outcome"], r["without"]["count"]) == (2, 50)
    assert "29%" in r["summary"] and "4%" in r["summary"]
    assert "not proof" in r["summary"]


def test_get_details_shows_comments(store):
    d = core.get_details(store, "Daniela")
    assert d["type"] == "Person"
    assert any("routing rule" in e.get("text", "") for e in d["edges"])


def test_rejects_mixed_or_unknown_anchors(store):
    with pytest.raises(ValueError):
        core.wander(store, ["cust_001", "queue_general"])
    with pytest.raises(ValueError):
        core.wander(store, ["nope"])


def test_other_members_breakdown(result):
    breakdown = result["convergence"][0]["other_members"]["breakdown"]
    assert breakdown["Ticket.status"] == {"open": 12, "closed": 10}


def test_claude_cannot_loosen_the_guardrails():
    from wander import tools
    spec = next(t for t in tools.GRAPH_TOOLS if t.name == "wander").input_schema
    assert set(spec["properties"]) == {"anchors"}
