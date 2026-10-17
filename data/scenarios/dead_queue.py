"""1. The dead queue — the article's scenario.

Five customers churned in Q3 2026, each giving the CRM a different reason. All five had
tickets routed to the Integrations queue after it was retired in the March support reorg,
where nobody picked them up. Twelve active customers have open tickets sitting there now.
"""

import datetime as dt

from data.company import INTEGRATION_FEATURES, GeneratorError, iso, random_date

NAME = "dead-queue"
TITLE = "The dead queue"
QUESTION = "Why did the five customers who churned in Q3 2026 leave?"
ANCHORS = {"type": "Customer", "where": {"churned_at": {"gte": "2026-07-01", "lte": "2026-09-30"}}}

RETIRED = "2026-03-15"
REASONS = ["Price", "Missing feature", "Moved to competitor", "Building in-house", "Budget"]
MANAGERS = ["Jenny", "Jenny", "Anshit", "Anshit", "Andrew"]
EARLIER_REASONS = [("Acquired by a larger group", "2026-02-11"), ("Company closed down", "2026-05-19")]


def plant(co, rng):
    churners = co.claim(5, NAME)
    at_risk = co.claim(12, NAME)
    earlier = co.claim(2, NAME)   # churned in H1 for unrelated reasons
    before = co.claim(10, NAME)   # used Integrations before it was retired; all resolved

    features = list(INTEGRATION_FEATURES)
    rng.shuffle(features)
    for c, reason, feature, manager in zip(churners, REASONS, features, MANAGERS):
        churned_at = dt.date.fromisoformat(random_date(rng, "2026-07-06", "2026-09-26"))
        created = random_date(rng, "2026-03-23", iso(churned_at - dt.timedelta(days=40)))
        topic, title = co.feature_ticket(feature)
        co.add_ticket(c, title, topic, created, "Integrations", feature, status="open")
        co.set(c, status="churned", churn_reason=reason, churned_at=iso(churned_at))
        co.set_manager(c, manager)

    for c in at_risk:
        for _ in range(rng.choice([1, 1, 2])):
            feature = rng.choice(INTEGRATION_FEATURES)
            topic, title = co.feature_ticket(feature)
            co.add_ticket(c, title, topic, random_date(rng, "2026-03-18", "2026-09-25"),
                          "Integrations", feature, status="open")
        co.set(c, health_score=rng.randint(22, 74))  # skews lower than most, not perfectly

    for c, (reason, churned_at) in zip(earlier, EARLIER_REASONS):
        co.set(c, status="churned", churn_reason=reason, churned_at=churned_at)

    for c in before:
        feature = rng.choice(INTEGRATION_FEATURES)
        topic, title = co.feature_ticket(feature)
        co.add_ticket(c, title, topic, random_date(rng, "2025-10-06", "2026-03-06"),
                      "Integrations", feature, status="closed")

    return {"churners": churners, "at_risk": at_risk, "earlier": earlier, "before": before}


def check(co, facts):
    churners, at_risk = set(facts["churners"]), set(facts["at_risk"])
    after = co.queue_reach("Integrations", since=RETIRED)
    if after != churners | at_risk:
        raise GeneratorError(f"{NAME}: expected 17 customers with Integrations tickets after "
                             f"{RETIRED}, found {len(after)}.")
    churned = {c for c in co.of_type("Customer") if co.props(c)["status"] == "churned"}
    if churned != churners | set(facts["earlier"]):
        raise GeneratorError(f"{NAME}: expected exactly 7 churned customers, found {len(churned)}.")
    if len({co.props(c)["churn_reason"] for c in churners}) != 5:
        raise GeneratorError(f"{NAME}: the five churn reasons must all differ.")
    if co.queue_reach("Integrations") & set(facts["before"]) != set(facts["before"]) or \
            set(facts["before"]) & (churners | at_risk):
        raise GeneratorError(f"{NAME}: pre-retirement Integrations customers must be separate from the 17.")
    qid = co.queue("Integrations")
    for c in at_risk:
        if not any(co.props(t)["status"] == "open" and co.edge_from("ROUTED_TO", t)["to"] == qid
                   and co.props(t)["created_at"] >= RETIRED for t in co.tickets_of(c)):
            raise GeneratorError(f"{NAME}: at-risk customer {c} has no open Integrations ticket.")
    dead = {e["from"] for e in co.edges if e["type"] == "ROUTED_TO" and e["to"] == qid
            and e["properties"]["routed_at"] >= RETIRED}
    if any(e["type"] == "ESCALATED_TO" and e["from"] in dead for e in co.edges):
        raise GeneratorError(f"{NAME}: no ticket in the dead queue may have been escalated.")


def expected(co, facts):
    return {
        "anchor_count": 5,
        "convergence": {"type": "Queue", "name": "Integrations"},
        "lift_range": [2.2, 2.8],
        "explanation_includes": ["Support reorg", "Reorg plan: support teams 2026", "Daniela"],
        "other_members_include": facts["at_risk"],
        "pruned_include": [
            {"name": "General support", "reason": "hub"},
            {"type": "Feature", "reason": "low support"},
            {"type": "Person", "reason": "low support"},
        ],
        "base_rate": {"node": "Integrations", "since": RETIRED, "outcome": "churned",
                      "with": [5, 17], "without": [2, 50]},
    }
