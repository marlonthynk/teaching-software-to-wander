"""The scenario framework.

A scenario is one module in this folder, listed in scenarios.yaml. It plants one story
into the base company and says, in a machine-checkable way, what the wander should find.
Each module defines:

    NAME, TITLE, QUESTION   the scenario's id, a short title, and the question a user would ask
    ANCHORS                 a selector: {"type": ..., "where": {...}} (see wander/stores/filters.py)
    plant(company, rng)     claims customers and adds what makes the story true; returns facts
    check(company, facts)   data-level checks, run after every scenario is planted
    expected(company, facts) the expected wander outcome (see verify.py for the keys)

Adding a scenario means adding one module and one line in scenarios.yaml. Nothing else.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import yaml

HERE = Path(__file__).resolve().parent


@dataclass
class Scenario:
    module: ModuleType

    @property
    def name(self) -> str:
        return self.module.NAME

    @property
    def title(self) -> str:
        return self.module.TITLE

    @property
    def question(self) -> str:
        return self.module.QUESTION

    @property
    def anchors(self) -> dict:
        return self.module.ANCHORS

    def plant(self, company, rng) -> dict:
        return self.module.plant(company, rng) or {}

    def check(self, company, facts: dict) -> None:
        self.module.check(company, facts)

    def expected(self, company, facts: dict) -> dict:
        return self.module.expected(company, facts)


def load_scenarios() -> list[Scenario]:
    order = yaml.safe_load((HERE / "scenarios.yaml").read_text())["scenarios"]
    scenarios = [Scenario(importlib.import_module(f"data.scenarios.{m}")) for m in order]
    names = [s.name for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError(f"Two scenarios share a name: {names}")
    return scenarios
