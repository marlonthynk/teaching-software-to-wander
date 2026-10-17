"""The guardrails that keep the wander from turning into noise.

Bounded: a hop limit and a node budget, both visible in the result when they bite.
Pruned: keep only where the anchors' paths converge more than you'd expect by chance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

DEFAULT_MAX_HOPS = 5
DEFAULT_EXPLAIN_HOPS = 3
DEFAULT_MIN_SUPPORT = 0.6
DEFAULT_MIN_LIFT = 2.0
DEFAULT_MAX_NODES = 500
MIN_SHARED_ANCHORS = 2   # a node only one anchor reaches isn't worth reporting


@dataclass(frozen=True)
class Settings:
    max_hops: int = DEFAULT_MAX_HOPS
    explain_hops: int = DEFAULT_EXPLAIN_HOPS
    min_support: float = DEFAULT_MIN_SUPPORT
    min_lift: float = DEFAULT_MIN_LIFT
    max_nodes: int = DEFAULT_MAX_NODES
    prune: bool = True

    def __post_init__(self):
        if not 1 <= self.max_hops <= 8:
            raise ValueError("max_hops must be between 1 and 8.")
        if not 0 <= self.explain_hops <= 5:
            raise ValueError("explain_hops must be between 0 and 5.")
        if not 0 < self.min_support <= 1:
            raise ValueError("min_support must be between 0 and 1.")
        if self.min_lift <= 1:
            raise ValueError("min_lift must be above 1 (1 means 'no more than chance').")
        if not 10 <= self.max_nodes <= 5000:
            raise ValueError("max_nodes must be between 10 and 5000.")

    @property
    def hub_share(self) -> float:
        """A node at least this share of the population reaches can never reach min_lift."""
        return 1 / self.min_lift


def lift(support: float, reach_share: float) -> float:
    return support / reach_share if reach_share else float("inf")


def classify(support: float, reach_share: float, settings: Settings) -> str:
    """'kept', or the reason a candidate was pruned."""
    if reach_share >= settings.hub_share:
        return "hub"
    if support < settings.min_support:
        return "low support"
    if lift(support, reach_share) < settings.min_lift:
        return "low lift"
    return "kept"


REASON_TEXT = {
    "hub": "most of the population reaches it this way, so sharing it says little",
    "low support": "too few of the starting points reach it",
    "low lift": "enough of the starting points share it, but no more than chance would give (a weak lead)",
}


def approx_tokens(payload) -> int:
    """Roughly how many tokens this would cost Claude to read (about 4 characters a token)."""
    return len(json.dumps(payload, default=str)) // 4
