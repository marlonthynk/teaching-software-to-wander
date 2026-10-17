"""5. The coincidence — a shared node that isn't a cause.

Four customers asked for refunds in August 2026. Three are managed by Jenny, but Jenny
manages almost half of all customers, so three of four is about what chance would give.
"""

from data.company import GeneratorError, random_date

NAME = "coincidence"
TITLE = "The coincidence"
QUESTION = "Why did the customers who asked for refunds in August 2026 ask for them?"
ANCHORS = {"type": "Customer", "where": {"refund_requested_at": {"gte": "2026-08-01", "lte": "2026-08-31"}}}

MANAGERS = ["Jenny", "Jenny", "Jenny", "Andrew"]
REFUNDS = [
    ("SSO", "Refund for SSO seats we never used"),
    ("Mobile app", "Refund request: mobile app unusable for a week"),
    ("Dashboards", "Refund for dashboard downtime in July"),
    ("CSV import", "Refund for an import add-on we can't use"),
]


def plant(co, rng):
    refunders = co.claim(4, NAME)
    for c, manager, (feature, title) in zip(refunders, MANAGERS, REFUNDS):
        requested = random_date(rng, "2026-08-03", "2026-08-28")
        co.add_ticket(c, title, "billing", requested, "Billing", feature, status="closed")
        co.set(c, refund_requested_at=requested)
        co.set_manager(c, manager)
    return {"refunders": refunders}


def check(co, facts):
    if co.select(ANCHORS) != sorted(facts["refunders"]):
        raise GeneratorError(f"{NAME}: the anchor selector must pick exactly the 4 refunders.")


def expected(co, facts):
    return {
        "anchor_count": 4,
        "convergence": None,
        "pruned_include": [{"name": "Jenny", "reason": "low lift", "lift_range": [1.5, 1.9]}],
    }
