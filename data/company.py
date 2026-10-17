"""The company builder: base data plus helpers that scenarios use to plant their stories."""

from __future__ import annotations

import datetime as dt
import random

from wander.stores.filters import matches

TODAY = dt.date(2026, 10, 1)  # "today" in the data. Never use the real clock.

# Ticket templates per feature: (topic, title)
FEATURE_TICKETS: dict[str, list[tuple[str, str]]] = {
    "Data sync": [
        ("bug", "Data sync stops halfway through"),
        ("bug", "Sync shows some records twice"),
        ("question", "How often does data sync run?"),
        ("feature request", "Sync custom fields as well"),
    ],
    "SSO": [
        ("question", "Setting up SSO with Okta"),
        ("bug", "SSO login loops back to the sign-in page"),
        ("feature request", "SSO for contractor accounts"),
        ("question", "Can we enforce SSO for everyone?"),
    ],
    "API rate limits": [
        ("bug", "API returns 429 errors under normal load"),
        ("question", "What are the API limits on our plan?"),
        ("feature request", "Higher API limits for bulk jobs"),
    ],
    "Webhooks": [
        ("bug", "Webhooks not firing on record updates"),
        ("question", "How do we verify webhook signatures?"),
        ("feature request", "Retry failed webhooks automatically"),
    ],
    "CSV import": [
        ("bug", "CSV import fails on accented characters"),
        ("question", "Largest file a CSV import can take?"),
        ("feature request", "Map columns when importing a CSV"),
    ],
    "Dashboards": [
        ("bug", "Dashboard widgets load slowly"),
        ("question", "Sharing a dashboard with a colleague"),
        ("feature request", "Dark mode for dashboards"),
    ],
    "Mobile app": [
        ("bug", "Mobile app logs us out every day"),
        ("question", "Is there an Android version of the app?"),
        ("feature request", "Offline mode in the mobile app"),
    ],
    "Advanced reporting": [
        ("feature request", "Custom reports with our own metrics"),
        ("feature request", "Scheduled reports sent by email"),
        ("feature request", "Export reports to Excel"),
        ("feature request", "Pivot tables in reports"),
        ("feature request", "Reports across several workspaces"),
        ("feature request", "Reports with year-on-year comparison"),
        ("feature request", "Better reporting than the basic dashboards"),
        ("feature request", "Report builder for our finance team"),
        ("feature request", "Drill down from a report into the records"),
        ("feature request", "Reporting API for our BI tool"),
    ],
}

GENERAL_TICKETS = [
    ("question", "Adding a new user to our account"),
    ("question", "Changing the account owner"),
    ("question", "Where do we find the release notes?"),
    ("bug", "Password reset email never arrived"),
    ("question", "Do you have a status page?"),
    ("question", "Training session for new staff"),
]

PLATFORM_TICKETS = [
    ("bug", "Workspace very slow this morning"),
    ("bug", "Error 500 when saving settings"),
    ("question", "Exporting the audit log"),
    ("question", "Moving data between workspaces"),
    ("bug", "Search results missing recent records"),
]

BILLING_TICKETS = [
    ("billing", "Invoice shows the wrong company address"),
    ("billing", "Updating our card details"),
    ("billing", "Copy of last month's invoice, please"),
    ("billing", "VAT number missing from our invoice"),
    ("billing", "Question about our renewal price"),
    ("billing", "Adding a purchase order number to invoices"),
]

INTEGRATION_FEATURES = ["Data sync", "SSO", "API rate limits", "Webhooks", "CSV import"]


def iso(d: dt.date) -> str:
    return d.isoformat()


def random_date(rng: random.Random, start: str, end: str) -> str:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return iso(a + dt.timedelta(days=rng.randint(0, (b - a).days)))


class GeneratorError(RuntimeError):
    """The generated data doesn't hold up. The message names what broke."""


class Company:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.pool: list[str] = []          # customers no scenario has claimed yet
        self.claims: dict[str, str] = {}   # customer id -> scenario name
        self.noise_tickets: set[str] = set()
        self._ticket_seq = 0

    # ---- building -------------------------------------------------------------

    def add_node(self, type_: str, id_: str, **props) -> str:
        if id_ in self.nodes:
            raise GeneratorError(f"Duplicate node id {id_}")
        self.nodes[id_] = {"id": id_, "type": type_, "properties": props}
        return id_

    def add_edge(self, type_: str, from_: str, to: str, **props) -> None:
        for end in (from_, to):
            if end not in self.nodes:
                raise GeneratorError(f"Edge {type_} refers to unknown node {end}")
        self.edges.append({"type": type_, "from": from_, "to": to, "properties": props})

    def set(self, id_: str, **props) -> None:
        self.nodes[id_]["properties"].update(props)

    def props(self, id_: str) -> dict:
        return self.nodes[id_]["properties"]

    def claim(self, n: int, by: str) -> list[str]:
        """Claim n customers for a scenario, so no two scenarios share a customer."""
        if len(self.pool) < n:
            raise GeneratorError(f"Scenario '{by}' needs {n} customers but only {len(self.pool)} are unclaimed.")
        chosen = sorted(self.rng.sample(self.pool, n))
        for c in chosen:
            if c in self.claims:
                raise GeneratorError(f"{c} is claimed by both '{self.claims[c]}' and '{by}'.")
            self.claims[c] = by
            self.pool.remove(c)
        return chosen

    def set_manager(self, customer: str, person_name: str) -> None:
        if self.manager_of(customer):
            raise GeneratorError(f"{customer} already has an account manager.")
        self.add_edge("MANAGES", self.person(person_name), customer)

    def add_ticket(self, customer: str, title: str, topic: str, created_at: str, queue: str,
                   feature: str | None = None, status: str = "closed", noise: bool = False) -> str:
        self._ticket_seq += 1
        tid = f"tkt_{self._ticket_seq:04d}"
        self.add_node("Ticket", tid, title=title, topic=topic, status=status, created_at=created_at)
        self.add_edge("RAISED", customer, tid)
        self.add_edge("ROUTED_TO", tid, self.queue(queue), routed_at=created_at)
        if feature:
            self.add_edge("ABOUT", tid, self.feature(feature))
        if noise:
            self.noise_tickets.add(tid)
        return tid

    def feature_ticket(self, feature: str, topic: str | None = None) -> tuple[str, str]:
        options = [t for t in FEATURE_TICKETS[feature] if topic is None or t[0] == topic]
        return self.rng.choice(options)

    # ---- looking things up ----------------------------------------------------

    def of_type(self, type_: str) -> list[str]:
        return [i for i, n in self.nodes.items() if n["type"] == type_]

    def _by_name(self, type_: str, name: str) -> str:
        for i, n in self.nodes.items():
            if n["type"] == type_ and n["properties"].get("name") == name:
                return i
        raise GeneratorError(f"No {type_} called {name}")

    def person(self, name: str) -> str:
        return self._by_name("Person", name)

    def feature(self, name: str) -> str:
        return self._by_name("Feature", name)

    def queue(self, name: str) -> str:
        return self._by_name("Queue", name)

    def select(self, selector: dict) -> list[str]:
        return sorted(i for i, n in self.nodes.items()
                      if n["type"] == selector["type"] and matches(n["properties"], selector.get("where")))

    def manager_of(self, customer: str) -> str | None:
        for e in self.edges:
            if e["type"] == "MANAGES" and e["to"] == customer:
                return e["from"]
        return None

    def tickets_of(self, customer: str) -> list[str]:
        return [e["to"] for e in self.edges if e["type"] == "RAISED" and e["from"] == customer]

    def edge_from(self, type_: str, from_: str) -> dict | None:
        for e in self.edges:
            if e["type"] == type_ and e["from"] == from_:
                return e
        return None

    def queue_of(self, ticket: str) -> str:
        return self.props(self.edge_from("ROUTED_TO", ticket)["to"])["name"]

    def feature_of(self, ticket: str) -> str | None:
        e = self.edge_from("ABOUT", ticket)
        return self.props(e["to"])["name"] if e else None

    def queue_reach(self, queue: str, since: str | None = None) -> set[str]:
        qid = self.queue(queue)
        tickets = {e["from"] for e in self.edges if e["type"] == "ROUTED_TO" and e["to"] == qid
                   and (since is None or e["properties"]["routed_at"] >= since)}
        return {e["from"] for e in self.edges if e["type"] == "RAISED" and e["to"] in tickets}

    def feature_reach(self, feature: str) -> set[str]:
        fid = self.feature(feature)
        tickets = {e["from"] for e in self.edges if e["type"] == "ABOUT" and e["to"] == fid}
        return {e["from"] for e in self.edges if e["type"] == "RAISED" and e["to"] in tickets}

    # ---- output -----------------------------------------------------------------

    def to_json(self) -> tuple[list[dict], list[dict]]:
        nodes = []
        for n in sorted(self.nodes.values(), key=lambda n: (n["type"], n["id"])):
            props = {k: v for k, v in sorted(n["properties"].items()) if v is not None}
            nodes.append({"id": n["id"], "type": n["type"], "properties": props})
        edges = sorted(
            ({"type": e["type"], "from": e["from"], "to": e["to"],
              "properties": dict(sorted(e["properties"].items()))} for e in self.edges),
            key=lambda e: (e["type"], e["from"], e["to"]),
        )
        return nodes, edges
