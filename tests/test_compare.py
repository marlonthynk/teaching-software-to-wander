"""Compare mode's "only in this answer" chips. No API key or Neo4j needed."""

import json
from pathlib import Path

import pytest

from wander.chat.compare import mentioned, names_of_things, only_in

ROOT = Path(__file__).resolve().parent.parent
NAMES = (("Integrations", "Queue"), ("Rosa", "Person"), ("Support reorg", "Decision"), ("Redwood Foods", "Customer"))


def test_names_come_from_the_data_without_tickets():
    kinds = {kind for _, kind in names_of_things()}
    assert "Ticket" not in kinds and {"Customer", "Queue", "Person"} <= kinds


def test_one_word_names_match_their_case_longer_ones_any_case():
    text = "Rosa said the support reorg moved integrations work. Rosalind agreed."
    assert [h["name"] for h in mentioned(text, NAMES)] == ["Rosa", "Support reorg"]


def test_only_in_keeps_what_the_other_answer_does_not_name():
    texts = {"records": "Redwood Foods left over price.",
             "graph": "Redwood Foods raised a ticket routed to the Integrations queue; Rosa commented."}
    assert only_in(texts, NAMES) == {
        "records": [],
        "graph": [{"name": "Integrations", "kind": "Queue"}, {"name": "Rosa", "kind": "Person"}],
    }


def test_the_compare_element_is_where_chainlit_looks():
    assert (ROOT / "public" / "elements" / "Compare.jsx").exists()
    assert 'name="Compare"' in (ROOT / "app.py").read_text()


@pytest.mark.filterwarnings("ignore::DeprecationWarning")  # from a library Chainlit loads
def test_the_starters_are_real_scenarios():
    import app

    names = {s["name"] for s in json.loads((ROOT / "data" / "generated" / "scenarios.json").read_text())}
    assert set(app.STARTERS) <= names and len(app._starters()) == len(app.STARTERS) == 2
