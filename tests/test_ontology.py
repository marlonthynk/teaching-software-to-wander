"""Proposing, reviewing and applying ontology changes, validation, and the "unlock" behaviour."""

import pytest

from data.load_graph import find_stale
from wander import proposals, tools
from wander.graph.lookups import find
from wander.graph.wander import wander
from wander import ontology as onto_mod
from wander.ontology import Ontology, OntologyError

RENEWAL = {"kind": "property", "entity": "Customer", "name": "renewal_date",
           "description": "When the customer's contract renews.", "proposed_by": "Mike"}
PARTNER = {"kind": "entity", "name": "Partner", "description": "A consulting firm that refers customers to us.",
           "properties": {"notes": "What we've agreed with them."}, "proposed_by": "Tom"}
REFERRED_BY = {"kind": "relationship", "name": "REFERRED_BY", "from": "Customer", "to": "Partner",
               "description": "The partner that referred this customer.", "proposed_by": "Tom"}


def q3(ctx):
    found = find(ctx.graph, "Customer", {"churned_at": {"gte": "2026-07-01", "lte": "2026-09-30"}})
    return [n["id"] for n in found["nodes"]]


def members(ctx):
    return wander(ctx.graph, q3(ctx))["convergence"][0]["other_members"]["members"]


def propose_and_apply(ctx, *changes, by="Marlon"):
    ids = [proposals.propose(c)["proposal"] for c in changes]
    return proposals.apply(ctx, ids, by)


def test_initial_ontology_has_seven_entities():
    onto = Ontology.load(onto_mod.INITIAL_PATH)
    assert len(onto.entities) == 7 and len(onto.relationships) == 7
    assert not onto.proposals and not onto.rejected


def test_real_ontology_file_is_untouched(ctx):
    live = onto_mod.ROOT / "ontology.yaml"
    before = live.read_bytes()
    propose_and_apply(ctx, RENEWAL)
    assert live.read_bytes() == before


def test_a_proposal_changes_nothing_until_applied(ctx, ontology_file):
    result = proposals.propose(RENEWAL)
    assert result["status"] == "pending review" and result["would_load"] == 60
    assert "waiting for a developer" in result["message"]
    onto = Ontology.load(ontology_file)
    assert "renewal_date" not in onto.entities["Customer"].properties
    assert [p["id"] for p in onto.proposals] == [result["proposal"]]
    assert not any("renewal_date" in m for m in members(ctx))


def test_renewal_dates_unlock_after_review(ctx, ontology_file):
    result = propose_and_apply(ctx, RENEWAL)
    assert result["applied"][0]["loaded"] == 60  # every active customer
    at_risk = [m for m in members(ctx) if any(s["status"] == "open" for t in m["through"] for s in t["via"])]
    assert len(at_risk) == 12 and all("renewal_date" in m for m in at_risk)

    entry = Ontology.load(ontology_file).changelog[-1]
    assert entry["by"] == "Mike" and entry["reviewed_by"] == "Marlon" and "renewal_date" in entry["change"]
    assert not Ontology.load(ontology_file).proposals

    ctx.graph.reload(onto_mod.reset(ontology_file))
    assert not any("renewal_date" in m for m in members(ctx))


def test_escalations_show_an_absence(ctx):
    propose_and_apply(ctx, {"kind": "relationship", "name": "ESCALATED_TO", "from": "Ticket", "to": "Person",
                            "description": "The ticket was escalated to this person.", "proposed_by": "Rosa"})
    steps = [s for m in members(ctx) for t in m["through"] for s in t["via"]]
    assert steps and all(s["escalated_to"] == "none" for s in steps if s["created_at"] >= "2026-03-15")


def test_partner_unlock_finds_northwind(ctx):
    overdue = [n["id"] for n in find(ctx.graph, "Customer", {"payment_status": "overdue"})["nodes"]]
    assert wander(ctx.graph, overdue)["convergence"] == []
    result = propose_and_apply(ctx, PARTNER, REFERRED_BY)
    assert [a["loaded"] for a in result["applied"]] == [2, 12]
    top = wander(ctx.graph, overdue)["convergence"][0]
    assert top["name"] == "Northwind Consulting" and "quarterly invoicing" in top["properties"]["notes"]


def test_proposals_can_build_on_each_other_but_apply_together(ctx, ontology_file):
    p1 = proposals.propose(PARTNER)["proposal"]
    p2 = proposals.propose(REFERRED_BY)["proposal"]  # valid on top of the pending Partner
    assert [p["valid"] for p in proposals.pending()["pending"]] == [True, True]
    with pytest.raises(OntologyError, match="apply that one too"):
        proposals.apply(ctx, [p2], "Marlon")
    assert len(Ontology.load(ontology_file).proposals) == 2  # nothing half-applied
    proposals.apply(ctx, [p1, p2], "Marlon")
    assert "REFERRED_BY" in Ontology.load(ontology_file).relationships


def test_rejecting_keeps_a_record(ctx, ontology_file):
    pid = proposals.propose(RENEWAL)["proposal"]
    with pytest.raises(OntologyError, match="who reviewed"):
        proposals.reject(pid, "", "Not now")
    proposals.reject(pid, "Marlon", "Finance owns this data; ask them first.")
    onto = Ontology.load(ontology_file)
    assert not onto.proposals
    assert onto.rejected[0]["reason"].startswith("Finance") and onto.rejected[0]["rejected_by"] == "Marlon"
    assert proposals.propose(RENEWAL)["proposal"] != pid  # ids are never reused


def test_applying_needs_a_reviewer(ctx):
    pid = proposals.propose(RENEWAL)["proposal"]
    with pytest.raises(OntologyError, match="who reviewed"):
        proposals.apply(ctx, [pid], " ")


def test_declared_without_data(ctx):
    result = proposals.propose({"kind": "relationship", "name": "OWNS", "from": "Person", "to": "Feature",
                                "description": "The person owns this part of the product.",
                                "proposed_by": "Charlene"})
    assert result["would_load"] == 0 and "No data found for it yet" in result["message"]


@pytest.mark.parametrize("change, message", [
    ({"kind": "entity", "name": "Customer", "description": "Again."}, "already declared"),
    ({"kind": "entity", "name": "partner", "description": "Lower case."}, "PascalCase"),
    ({"kind": "relationship", "name": "REFERRED_BY", "from": "Customer", "to": "Partner",
      "description": "Partner isn't declared or proposed."}, "Declare it first"),
    ({"kind": "relationship", "name": "referred by", "from": "Customer", "to": "Ticket",
      "description": "Bad name."}, "UPPER_SNAKE_CASE"),
    ({"kind": "property", "entity": "Customer", "name": "status", "description": "Duplicate."}, "already has"),
    ({"kind": "property", "entity": "Nope", "name": "x", "description": "Unknown entity."}, "isn't a declared"),
    ({"kind": "property", "entity": "Customer", "name": "renewal_date", "description": ""}, "describe it"),
    ({"kind": "property", "entity": "Customer", "name": "id", "description": "Reserved."}, "reserved"),
    ({"kind": "thing", "name": "X", "description": "Bad kind."}, "kind must be"),
])
def test_validation_happens_when_proposing(ctx, ontology_file, change, message):
    before = ontology_file.read_text()
    with pytest.raises(OntologyError, match=message):
        proposals.propose({"proposed_by": "test", **change})
    assert ontology_file.read_text() == before


def test_a_proposal_needs_a_proposer(ctx):
    with pytest.raises(OntologyError, match="who is proposing"):
        proposals.propose({**RENEWAL, "proposed_by": ""})


def test_the_chat_cannot_change_the_ontology():
    for toolset in tools.TOOLSETS.values():
        assert "propose_change" not in {t.name for t in toolset}


def test_reset_drops_pending_proposals(ctx, ontology_file):
    proposals.propose(RENEWAL)
    assert not onto_mod.reset(ontology_file).proposals


def test_stale_constraints_are_found():
    onto = Ontology.load(onto_mod.INITIAL_PATH)
    rows = [{"name": "customer_id", "labelsOrTypes": ["Customer"]},
            {"name": "partner_id", "labelsOrTypes": ["Partner"]},
            {"name": "someone_elses", "labelsOrTypes": ["Partner"]}]
    assert find_stale(rows, onto) == ["partner_id"]
