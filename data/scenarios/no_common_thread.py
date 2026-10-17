"""3. No common thread — the control. The wander must find nothing, and say so.

Four customers downgraded in Q2 2026 for scattered reasons. No account manager has more
than two of them, and nothing outside the hubs is shared by three or more.
"""

import math
from collections import Counter

from data.company import GeneratorError, random_date

NAME = "no-common-thread"
TITLE = "No common thread"
QUESTION = "Why did the customers who downgraded their plan in Q2 2026 downgrade?"
ANCHORS = {"type": "Customer", "where": {"plan_change": "downgrade",
                                         "plan_changed_at": {"gte": "2026-04-01", "lte": "2026-06-30"}}}

MANAGERS = ["Jenny", "Anshit", "Andrew", "Jenny"]  # no account manager has more than 2 of them
MIN_SUPPORT = 0.6                                   # the wander's default threshold


def plant(co, rng):
    downgraders = co.claim(4, NAME)
    for c, manager in zip(downgraders, MANAGERS):
        co.set(c, plan="Starter", plan_change="downgrade",
               plan_changed_at=random_date(rng, "2026-04-03", "2026-06-29"))
        co.set_manager(c, manager)
    return {"downgraders": downgraders}


def check(co, facts):
    anchors = facts["downgraders"]
    if co.select(ANCHORS) != sorted(anchors):
        raise GeneratorError(f"{NAME}: the anchor selector must pick exactly the 4 downgraders.")
    # No node outside the hubs may be shared by as many anchors as min_support needs (3 of 4).
    # A lower reach wouldn't help here: it would make an accidental match's lift higher.
    threshold = math.ceil(MIN_SUPPORT * len(anchors))
    n = len(co.of_type("Customer"))
    shared = Counter()
    for c in anchors:
        near = {co.manager_of(c)}
        for t in co.tickets_of(c):
            near |= {t, co.edge_from("ROUTED_TO", t)["to"]}
            about = co.edge_from("ABOUT", t)
            if about:
                near.add(about["to"])
        shared.update(near - {None})
    for node, count in shared.items():
        if count < threshold:
            continue
        p = co.props(node)
        if co.nodes[node]["type"] == "Queue" and len(co.queue_reach(p["name"])) >= n / 2:
            continue  # a hub: most customers share it, so it says nothing
        raise GeneratorError(f"{NAME}: {p.get('name', node)} is shared by {count} of the "
                             f"{len(anchors)} downgraders; only hubs may be.")


def expected(co, facts):
    return {
        "anchor_count": 4,
        "convergence": None,
        "pruned_include": [{"type": "Queue", "reason": "hub"}],
    }
