"""Build the fictional company and plant the scenarios. Deterministic (seed 42).

    uv run python -m data.generate

Two layers: a base company full of ordinary noise, then the scenarios in
data/scenarios/, each planting one story. The output in data/generated/ is committed, so
every reader gets identical data. The generator checks its own constraints and every
scenario's data-level facts, and fails loudly rather than writing data that only nearly works.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from data.company import (BILLING_TICKETS, GENERAL_TICKETS, PLATFORM_TICKETS, TODAY, Company,
                          GeneratorError, iso, random_date)
from data.scenarios import load_scenarios

SEED = 42
OUT = Path(__file__).resolve().parent / "generated"
N_CUSTOMERS = 67
WINDOW_START = "2025-10-01"           # tickets in the data run from here to TODAY
MANAGER_BOOKS = {"Jenny": 30, "Anshit": 20, "Andrew": 17}
NOISE_MIN_SUPPORT = 0.6               # matches the wander's default min_support

PEOPLE = [
    ("Charlene", "Product manager", "Product"),
    ("Daniela", "Integrations support lead", "Support"),
    ("Tom", "Head of Partnerships", "Partnerships"),
    ("Anshit", "Account manager", "Customer Success"),
    ("Andrew", "Account manager", "Customer Success"),
    ("Jenny", "Account manager", "Customer Success"),
    ("Dominus", "Head of Customer Success", "Customer Success"),
    ("Mike", "CFO", "Finance"),
    ("Rosa", "Head of Support", "Support"),
    ("Priya", "Support agent", "Support"),
    ("Lukas", "Support agent", "Support"),
    ("Sofia", "Support agent", "Support"),
    ("Kwame", "Support agent", "Support"),
    ("Ben", "Finance analyst", "Finance"),
    ("Hana", "Engineering manager", "Engineering"),
]

FEATURES = [
    ("Data sync", "Integrations", "2023-02-14"),
    ("SSO", "Security", "2023-06-01"),
    ("API rate limits", "API", "2023-09-12"),
    ("Webhooks", "API", "2024-01-22"),
    ("CSV import", "Data", "2022-11-03"),
    ("Dashboards", "Analytics", "2022-05-10"),
    ("Mobile app", "Apps", "2024-07-08"),
    ("Advanced reporting", "Analytics", "2026-04-01"),
]

QUEUES = [
    ("queue_general", "General support"),
    ("queue_billing", "Billing"),
    ("queue_platform", "Platform"),
    ("queue_integrations", "Integrations"),
]

PLANS = ["Starter", "Growth", "Growth", "Enterprise"]

NAME_PREFIXES = ["Acme", "Apex", "Birch", "Bluefin", "Brightline", "Cedar", "Cobalt", "Copper", "Delta",
                 "Ember", "Evergreen", "Falcon", "Fernway", "Granite", "Helix", "Iris", "Juniper",
                 "Keystone", "Lumen", "Maple", "Meridian", "Nimbus", "Northstar", "Oakridge", "Orbit",
                 "Pinnacle", "Quarry", "Redwood", "Riverstone", "Saffron", "Silverline", "Summit",
                 "Tidal", "Upland", "Vertex", "Willow", "Zephyr"]
NAME_SUFFIXES = ["Analytics", "Logistics", "Health", "Foods", "Labs", "Retail", "Studios", "Systems",
                 "Energy", "Travel", "Media", "Freight"]

REORG_PLAN = (
    "Support reorg, effective 15 March 2026.\n\n"
    "Why: the Integrations team is small and its volume has been falling, while Platform "
    "support is stretched. We'll merge the two.\n\n"
    "What changes: the Integrations queue is retired on 15 March. Integrations specialists "
    "join Platform support. General support and Billing are unchanged.\n\n"
    "Owner: Rosa (Head of Support)."
)

DECISIONS = [
    ("dec_support_reorg", "Support reorg", "2026-03-02",
     "Merge the Integrations support team into Platform support and retire the Integrations queue "
     "on 15 March 2026.",
     ("doc_reorg_plan", "Reorg plan: support teams 2026", "plan", REORG_PLAN)),
    ("dec_pricing_update", "Pricing update", "2026-01-10",
     "Raise Growth and Enterprise list prices by 6% for new customers from February 2026.",
     ("doc_pricing_memo", "Pricing update memo", "memo",
      "From 1 February 2026, Growth and Enterprise list prices rise by 6% for new customers. "
      "Existing customers keep their price until renewal. Starter is unchanged.")),
    ("dec_sla_policy", "New SLA policy", "2026-05-20",
     "Enterprise customers get a first response within 4 working hours; others within 1 working day.",
     ("doc_sla_policy", "SLA policy v2", "policy",
      "First response times: Enterprise within 4 working hours, Growth and Starter within one working "
      "day. Breaches are reported weekly to the Head of Customer Success.")),
]

OTHER_DOCUMENTS = [
    ("doc_roadmap", "Product roadmap 2026", "roadmap",
     "H1: Advanced reporting (custom reports, scheduled exports), released 1 April. Mobile app "
     "offline mode. H2: workspace permissions, a refreshed dashboard designer."),
    ("doc_onboarding", "Customer onboarding guide", "guide",
     "Week one: set up users and SSO. Week two: connect data sources with data sync or CSV import. "
     "Week three: build the first dashboards. Raise a ticket with support at any point."),
    ("doc_partner_programme", "Partner programme overview", "overview",
     "We work with two referral partners, Northwind Consulting and Blue Harbour Advisory. Partners "
     "introduce customers and help them get started; we pay a referral fee for the first year."),
]

COMMENTS = [  # (person, document, date, text)
    ("Rosa", "doc_reorg_plan", "2026-03-03",
     "Agreed. Platform support picks up integration work from 15 March."),
    ("Daniela", "doc_reorg_plan", "2026-03-04",
     "Before we retire the Integrations queue: the routing rule still sends integration tickets "
     "there. We need to update it, or they'll go nowhere."),
    ("Mike", "doc_pricing_memo", "2026-01-08", "Fine by finance. Let's keep an eye on Starter churn."),
    ("Charlene", "doc_pricing_memo", "2026-01-09", "Can we keep the old price for customers mid-trial?"),
    ("Dominus", "doc_sla_policy", "2026-05-18", "Good. I'll add SLA breaches to the weekly CS review."),
    ("Charlene", "doc_roadmap", "2025-12-15", "Advanced reporting is the most requested feature this year."),
]

ESCALATE_TO = ["Rosa", "Priya", "Lukas", "Sofia", "Kwame", "Dominus"]


def build() -> tuple[Company, list, dict]:
    rng = random.Random(SEED)
    co = Company(rng)
    _base(co, rng)
    scenarios = load_scenarios()
    facts = {s.name: s.plant(co, rng) for s in scenarios}
    _assign_managers(co, rng)
    _noise_tickets(co, rng)
    _decorrelate(co, rng, scenarios, facts)
    _hidden_data(co, rng)
    _check_constraints(co)
    for s in scenarios:
        s.check(co, facts[s.name])
    return co, scenarios, facts


def _base(co: Company, rng: random.Random) -> None:
    for name, role, team in PEOPLE:
        co.add_node("Person", f"person_{name.lower()}", name=name, role=role, team=team)
    for name, area, released in FEATURES:
        co.add_node("Feature", "feat_" + name.lower().replace(" ", "_"), name=name, area=area,
                    released_at=released)
    for qid, name in QUEUES:
        co.add_node("Queue", qid, name=name, status="active")
    co.set("queue_integrations", status="retired", retired_at="2026-03-15")

    for did, title, date, summary, (doc_id, doc_title, doc_type, text) in DECISIONS:
        co.add_node("Decision", did, title=title, date=date, summary=summary)
        co.add_node("Document", doc_id, title=doc_title, type=doc_type, text=text)
        co.add_edge("DOCUMENTED_IN", did, doc_id)
    for doc_id, title, doc_type, text in OTHER_DOCUMENTS:
        co.add_node("Document", doc_id, title=title, type=doc_type, text=text)
    co.add_edge("RETIRED_BY", "queue_integrations", "dec_support_reorg")
    for person, doc, date, text in COMMENTS:
        co.add_edge("COMMENTED_ON", co.person(person), doc, date=date, text=text)

    names = rng.sample([f"{p} {s}" for p in NAME_PREFIXES for s in NAME_SUFFIXES], N_CUSTOMERS)
    for i, name in enumerate(names, start=1):
        cid = f"cust_{i:03d}"
        co.add_node("Customer", cid, name=name, status="active", plan=rng.choice(PLANS),
                    plan_change="none", payment_status="current")
        co.pool.append(cid)


def _assign_managers(co: Company, rng: random.Random) -> None:
    unmanaged = [c for c in co.of_type("Customer") if not co.manager_of(c)]
    rng.shuffle(unmanaged)
    for person, book in MANAGER_BOOKS.items():
        have = sum(1 for e in co.edges if e["type"] == "MANAGES" and e["from"] == co.person(person))
        need = book - have
        if need < 0 or need > len(unmanaged):
            raise GeneratorError(f"Can't give {person} a book of {book} customers.")
        for c in unmanaged[:need]:
            co.set_manager(c, person)
        unmanaged = unmanaged[need:]
    if unmanaged:
        raise GeneratorError(f"{len(unmanaged)} customers have no account manager.")


def _established_features() -> list[str]:
    """Noise tickets are only about features that existed before the data window starts."""
    return [name for name, _, released in FEATURES if released < WINDOW_START]


def _noise_tickets(co: Company, rng: random.Random) -> None:
    features = _established_features()
    for c in co.of_type("Customer"):
        p = co.props(c)
        end = p.get("churned_at") or iso(TODAY)
        for _ in range(rng.randint(3, 5)):
            created = random_date(rng, WINDOW_START, end)
            queue = rng.choices(["General support", "Billing", "Platform"], weights=[50, 25, 25])[0]
            feature = None
            if queue == "Billing":
                topic, title = rng.choice(BILLING_TICKETS)
            elif rng.random() < (0.6 if queue == "Platform" else 0.2):
                feature = rng.choice(features)
                topic, title = co.feature_ticket(feature)
            else:
                topic, title = rng.choice(PLATFORM_TICKETS if queue == "Platform" else GENERAL_TICKETS)
            recent = created >= "2026-09-10" and p["status"] == "active"
            status = "open" if recent and rng.random() < 0.6 else "closed"
            co.add_ticket(c, title, topic, created, queue, feature, status=status, noise=True)


def _decorrelate(co: Company, rng: random.Random, scenarios, facts) -> None:
    """Make sure noise doesn't plant an accidental shared feature among any scenario's anchors.

    Only noise tickets are moved, and only features a scenario doesn't itself expect to find.
    """
    established = _established_features()
    for s in scenarios:
        anchors = co.select(s.anchors)
        threshold = math.ceil(NOISE_MIN_SUPPORT * len(anchors))
        expected = s.expected(co, facts[s.name]).get("convergence") or {}
        protected = expected.get("name") if expected.get("type") == "Feature" else None
        for _ in range(100):
            touches = {f: {a for a in anchors if f in _features_of(co, a)} for f in established}
            over = [f for f in established if f != protected and len(touches[f]) >= threshold]
            if not over:
                break
            feature = over[0]
            movable = [t for a in sorted(touches[feature]) for t in co.tickets_of(a)
                       if t in co.noise_tickets and co.feature_of(t) == feature]
            if not movable:
                raise GeneratorError(f"{s.name}: {feature} is shared by too many anchors and can't be moved.")
            ticket = movable[0]
            target = min((f for f in established if f not in (feature, protected)),
                         key=lambda f: (len(touches[f]), f))
            edge = co.edge_from("ABOUT", ticket)
            edge["to"] = co.feature(target)
            topic, title = co.feature_ticket(target)
            co.set(ticket, topic=topic, title=title)
        else:
            raise GeneratorError(f"{s.name}: couldn't spread the anchors' features out.")


def _features_of(co: Company, customer: str) -> set[str]:
    return {f for t in co.tickets_of(customer) if (f := co.feature_of(t))}


def _hidden_data(co: Company, rng: random.Random) -> None:
    """Data that exists but isn't in the initial ontology (finance, support, customer success)."""
    for c in co.of_type("Customer"):
        p = co.props(c)
        if p["status"] == "active":
            co.set(c, renewal_date=random_date(rng, "2026-10-08", "2027-09-30"))
        if "health_score" not in p:
            co.set(c, health_score=rng.randint(30, 96) if p["status"] == "active" else rng.randint(15, 60))
    for t in sorted(co.noise_tickets):
        if rng.random() < 0.15:
            co.add_edge("ESCALATED_TO", t, co.person(rng.choice(ESCALATE_TO)))


def _check_constraints(co: Company) -> None:
    n = len(co.of_type("Customer"))
    for queue, minimum in (("General support", 55), ("Billing", 35), ("Platform", 35)):
        reach = len(co.queue_reach(queue))
        if reach < minimum:
            raise GeneratorError(f"{queue} reaches {reach} customers; it needs at least {minimum} to be a hub.")
    for name, _, _ in FEATURES:
        reach = len(co.feature_reach(name))
        if reach >= 0.35 * n:
            raise GeneratorError(f"{name} reaches {reach} of {n} customers; features must stay below 35%.")
    for person, book in MANAGER_BOOKS.items():
        have = sum(1 for e in co.edges if e["type"] == "MANAGES" and e["from"] == co.person(person))
        if have != book:
            raise GeneratorError(f"{person} manages {have} customers, expected {book}.")


def write(co: Company, scenarios, facts, out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    nodes, edges = co.to_json()
    manifest = [{"name": s.name, "title": s.title, "question": s.question, "anchors": s.anchors,
                 "expected": s.expected(co, facts[s.name])} for s in scenarios]
    for filename, payload in (("nodes.json", nodes), ("edges.json", edges), ("scenarios.json", manifest)):
        (out / filename).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


def main() -> None:
    co, scenarios, facts = build()   # build() fails loudly if any constraint or scenario fact breaks
    write(co, scenarios, facts)
    counts: dict[str, int] = {}
    for node in co.nodes.values():
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    print("Generated", ", ".join(f"{v} {k}" for k, v in sorted(counts.items())),
          f"and {len(co.edges)} edges into {OUT}")
    print("To check the wander finds every story: load Neo4j, then run `uv run pytest tests/test_scenarios.py`.")


if __name__ == "__main__":
    main()
