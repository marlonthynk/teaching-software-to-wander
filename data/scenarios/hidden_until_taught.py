"""4. Hidden until the business teaches it.

Six customers are paying late. Five were referred by Northwind Consulting, which promised
its clients quarterly invoicing; the company bills monthly. Partners and referrals are in
the data, but not in the initial ontology, so the graph can't see them until someone adds
them.
"""

from data.company import GeneratorError, random_date

NAME = "hidden-until-taught"
TITLE = "Hidden until the business teaches it"
QUESTION = "Why are our overdue customers paying late?"
ANCHORS = {"type": "Customer", "where": {"payment_status": "overdue"}}

NORTHWIND = "Northwind Consulting"
MANAGERS = ["Jenny", "Jenny", "Anshit", "Anshit", "Andrew", "Andrew"]  # at most 2 each

ONTOLOGY_ADDITIONS = [
    {"kind": "entity", "name": "Partner",
     "description": "A consulting firm that refers customers to us.",
     "properties": {"name": "The partner's name.",
                    "notes": "What we've agreed with them, and anything to know.",
                    "owner": "Who looks after the relationship."},
     "proposed_by": "Tom"},
    {"kind": "relationship", "name": "REFERRED_BY", "from": "Customer", "to": "Partner",
     "description": "The partner that referred this customer to us.",
     "proposed_by": "Tom"},
]


def plant(co, rng):
    overdue = co.claim(6, NAME)
    northwind_current = co.claim(3, NAME)
    blue_harbour_current = co.claim(3, NAME)

    nw = co.add_node("Partner", "partner_northwind", name=NORTHWIND, owner="Tom",
                     notes="Referral partner since 2025. Promised the clients it refers quarterly "
                           "invoicing as part of its consulting package. We bill monthly.")
    bh = co.add_node("Partner", "partner_blue_harbour", name="Blue Harbour Advisory", owner="Tom",
                     notes="Referral partner since 2024. Refers mid-sized retailers. No special terms.")

    northwind_overdue, blue_harbour_overdue = overdue[:5], overdue[5:]
    for c in northwind_overdue + northwind_current:
        co.add_edge("REFERRED_BY", c, nw)
    for c in blue_harbour_overdue + blue_harbour_current:
        co.add_edge("REFERRED_BY", c, bh)

    for c, manager in zip(overdue, MANAGERS):
        co.set(c, payment_status="overdue")
        co.set_manager(c, manager)
    for c in northwind_overdue[:3]:
        co.add_ticket(c, "Can we be invoiced quarterly instead?", "billing",
                      random_date(rng, "2026-06-01", "2026-09-20"), "Billing", status="closed")
    return {"overdue": overdue, "northwind_overdue": northwind_overdue,
            "northwind_current": northwind_current}


def check(co, facts):
    if co.select(ANCHORS) != sorted(facts["overdue"]):
        raise GeneratorError(f"{NAME}: the anchor selector must pick exactly the 6 overdue customers.")
    managers = [co.manager_of(c) for c in facts["overdue"]]
    if max(managers.count(m) for m in set(managers)) > 2:
        raise GeneratorError(f"{NAME}: no account manager may have more than 2 of the overdue customers.")
    referred = [e["from"] for e in co.edges if e["type"] == "REFERRED_BY" and e["to"] == "partner_northwind"]
    if len(referred) != 8:
        raise GeneratorError(f"{NAME}: Northwind must have referred 8 customers, found {len(referred)}.")


def expected(co, facts):
    return {
        "anchor_count": 6,
        "before_ontology": {"convergence": None},
        "ontology_additions": ONTOLOGY_ADDITIONS,
        "convergence": {"type": "Partner", "name": NORTHWIND},
        "lift_range": [5.0, 9.0],
        "other_members_exact": facts["northwind_current"],
    }
