"""Every scenario's expected outcome, parametrised over scenarios.json.

Adding a scenario adds a case here automatically.
"""

import json
from pathlib import Path

import pytest

from data.scenarios.verify import check

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = json.loads((ROOT / "data" / "generated" / "scenarios.json").read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario(scenario, store):
    assert check(scenario, store) == []


def test_the_wander_knows_nothing_about_any_scenario():
    forbidden = set()
    for s in SCENARIOS:
        forbidden |= {s["name"], s["title"], s["question"]}
        conv = s["expected"].get("convergence")
        if conv:
            forbidden.add(conv["name"])
    for path in (ROOT / "wander").rglob("*.py"):
        text = path.read_text()
        for word in forbidden:
            assert word not in text, f"{path.name} mentions {word!r}"
