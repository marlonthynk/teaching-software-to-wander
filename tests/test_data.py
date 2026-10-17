"""The planted numbers hold in the committed data."""

import json
from collections import Counter
from pathlib import Path

import pytest

from data import generate

GEN = Path(__file__).resolve().parent.parent / "data" / "generated"
RETIRED = "2026-03-15"


@pytest.fixture(scope="module")
def data():
    nodes = {n["id"]: n for n in json.loads((GEN / "nodes.json").read_text())}
    edges = json.loads((GEN / "edges.json").read_text())
    return nodes, edges


def customers(nodes):
    return {i: n["properties"] for i, n in nodes.items() if n["type"] == "Customer"}


def integrations_customers(nodes, edges, since=None):
    tickets = {e["from"] for e in edges if e["type"] == "ROUTED_TO" and e["to"] == "queue_integrations"
               and (since is None or e["properties"]["routed_at"] >= since)}
    return {e["from"] for e in edges if e["type"] == "RAISED" and e["to"] in tickets}


def test_generator_is_deterministic_and_matches_committed_data(tmp_path):
    co, scenarios, facts = generate.build()
    generate.write(co, scenarios, facts, tmp_path)
    for name in ("nodes.json", "edges.json", "scenarios.json"):
        assert (tmp_path / name).read_bytes() == (GEN / name).read_bytes(), name


def test_scale(data):
    nodes, _ = data
    counts = Counter(n["type"] for n in nodes.values())
    assert counts["Customer"] == 67
    assert 280 <= counts["Ticket"] <= 340
    assert counts["Queue"] == 4 and counts["Feature"] == 8 and counts["Decision"] == 3
    assert counts["Document"] == 6 and counts["Partner"] == 2
    assert 14 <= counts["Person"] <= 16


def test_exactly_five_churned_in_q3_with_different_reasons(data):
    nodes, _ = data
    churned = {i: p for i, p in customers(nodes).items() if p["status"] == "churned"}
    q3 = {i: p for i, p in churned.items() if "2026-07-01" <= p["churned_at"] <= "2026-09-30"}
    h1 = {i: p for i, p in churned.items() if "2026-01-01" <= p["churned_at"] <= "2026-06-30"}
    assert len(q3) == 5
    assert len({p["churn_reason"] for p in q3.values()}) == 5
    assert len(h1) == 2
    assert len(churned) == 7


def test_seventeen_customers_in_the_dead_queue(data):
    nodes, edges = data
    after = integrations_customers(nodes, edges, since=RETIRED)
    cs = customers(nodes)
    assert len(after) == 17
    churned = {c for c in after if cs[c]["status"] == "churned"}
    assert len(churned) == 5
    assert all("2026-07-01" <= cs[c]["churned_at"] <= "2026-09-30" for c in churned)
    # each of the 12 active ones has at least one open ticket there, raised after retirement
    ticket_props = {i: n["properties"] for i, n in nodes.items() if n["type"] == "Ticket"}
    dead = {e["from"] for e in edges if e["type"] == "ROUTED_TO" and e["to"] == "queue_integrations"
            and e["properties"]["routed_at"] >= RETIRED}
    for c in after - churned:
        theirs = {e["to"] for e in edges if e["type"] == "RAISED" and e["from"] == c}
        assert any(ticket_props[t]["status"] == "open" for t in theirs & dead), c


def test_base_rate_numbers(data):
    nodes, edges = data
    cs = customers(nodes)
    after = integrations_customers(nodes, edges, since=RETIRED)
    others = set(cs) - after
    assert sum(cs[c]["status"] == "churned" for c in after) == 5
    assert (len(others), sum(cs[c]["status"] == "churned" for c in others)) == (50, 2)


def test_queue_hubs_and_integrations_reach(data):
    nodes, edges = data
    reach = Counter()
    ticket_queue = {e["from"]: e["to"] for e in edges if e["type"] == "ROUTED_TO"}
    for queue in set(ticket_queue.values()):
        reach[queue] = len({e["from"] for e in edges if e["type"] == "RAISED"
                            and ticket_queue[e["to"]] == queue})
    assert reach["queue_general"] >= 55
    assert reach["queue_billing"] >= 35 and reach["queue_platform"] >= 35
    # the ~10 pre-retirement customers are separate from the 17, so all-time reach is ~27
    assert len(integrations_customers(nodes, edges)) == 27


def test_features_stay_below_a_third(data):
    nodes, edges = data
    about = {e["from"]: e["to"] for e in edges if e["type"] == "ABOUT"}
    for f in (i for i, n in nodes.items() if n["type"] == "Feature"):
        reach = {e["from"] for e in edges if e["type"] == "RAISED" and about.get(e["to"]) == f}
        assert len(reach) < 0.35 * 67, f


def test_account_manager_books(data):
    nodes, edges = data
    books = Counter(nodes[e["from"]]["properties"]["name"] for e in edges if e["type"] == "MANAGES")
    assert books == {"Jenny": 30, "Anshit": 20, "Andrew": 17}


def test_daniela_commented_on_the_reorg_plan(data):
    nodes, edges = data
    comment = next(e for e in edges if e["type"] == "COMMENTED_ON" and e["from"] == "person_daniela")
    assert comment["to"] == "doc_reorg_plan" and comment["properties"]["date"] == "2026-03-04"
    assert "routing rule" in comment["properties"]["text"]
    assert {"type": "RETIRED_BY", "from": "queue_integrations", "to": "dec_support_reorg",
            "properties": {}} in edges


def test_hidden_data_exists(data):
    nodes, edges = data
    cs = customers(nodes)
    assert all("renewal_date" in p for p in cs.values() if p["status"] == "active")
    assert all("health_score" in p for p in cs.values())
    referred = Counter(e["to"] for e in edges if e["type"] == "REFERRED_BY")
    assert referred["partner_northwind"] == 8
    escalated = {e["from"] for e in edges if e["type"] == "ESCALATED_TO"}
    dead = {e["from"] for e in edges if e["type"] == "ROUTED_TO" and e["to"] == "queue_integrations"
            and e["properties"]["routed_at"] >= RETIRED}
    assert escalated and not escalated & dead


def test_scenarios_dont_share_customers():
    co, scenarios, facts = generate.build()
    assert len(co.claims) == len(set(co.claims))
    anchor_sets = [set(co.select(s.anchors)) for s in scenarios]
    for i, a in enumerate(anchor_sets):
        for b in anchor_sets[i + 1:]:
            assert not a & b


def test_scenario_three_check_catches_an_accidental_shared_feature():
    from data.company import GeneratorError
    co, scenarios, facts = generate.build()
    s3 = next(s for s in scenarios if s.name == "no-common-thread")
    downgraders = facts[s3.name]["downgraders"]
    for c in downgraders[:3]:
        co.add_ticket(c, "Dark mode for dashboards", "feature request", "2026-05-01",
                      "General support", "Dashboards")
    with pytest.raises(GeneratorError, match="Dashboards is shared by 3 of the 4"):
        s3.check(co, facts[s3.name])
