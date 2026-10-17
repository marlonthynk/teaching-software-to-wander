"""2. The feature that sells — a positive story, on a different path.

Six customers upgraded in Q2 2026. Each had asked for Advanced reporting before it was
released on 1 April. Four others asked too but haven't upgraded yet.
"""

from data.company import GeneratorError, random_date

NAME = "feature-that-sells"
TITLE = "The feature that sells"
QUESTION = "Why did the customers who upgraded their plan in Q2 2026 upgrade?"
ANCHORS = {"type": "Customer", "where": {"plan_change": "upgrade",
                                         "plan_changed_at": {"gte": "2026-04-01", "lte": "2026-06-30"}}}

FEATURE = "Advanced reporting"
MANAGERS = ["Jenny", "Jenny", "Anshit", "Anshit", "Andrew", "Andrew"]


def plant(co, rng):
    upgraders = co.claim(6, NAME)
    askers = co.claim(4, NAME)
    for c, manager in zip(upgraders, MANAGERS):
        for _ in range(rng.choice([1, 2])):
            _ask(co, rng, c)
        co.set(c, plan="Enterprise", plan_change="upgrade",
               plan_changed_at=random_date(rng, "2026-04-06", "2026-06-26"))
        co.set_manager(c, manager)
    for c in askers:
        _ask(co, rng, c)
        co.set(c, plan="Growth")
    return {"upgraders": upgraders, "askers": askers}


def _ask(co, rng, customer):
    topic, title = co.feature_ticket(FEATURE, "feature request")
    co.add_ticket(customer, title, topic, random_date(rng, "2025-11-03", "2026-03-27"),
                  rng.choice(["General support", "Platform"]), FEATURE, status="closed")


def check(co, facts):
    reach = co.feature_reach(FEATURE)
    if reach != set(facts["upgraders"]) | set(facts["askers"]):
        raise GeneratorError(f"{NAME}: only the 6 upgraders and 4 askers may have {FEATURE} "
                             f"tickets; found {len(reach)} customers.")
    if co.select(ANCHORS) != sorted(facts["upgraders"]):
        raise GeneratorError(f"{NAME}: the anchor selector must pick exactly the 6 upgraders.")


def expected(co, facts):
    return {
        "anchor_count": 6,
        "convergence": {"type": "Feature", "name": FEATURE},
        "lift_range": [5.0, 8.0],
        "other_members_exact": facts["askers"],
        "pruned_include": [{"type": "Queue", "reason": "hub"}],
    }
