"""The guardrails that keep the wander from turning into noise, in one place.

Bounded — how far the walk goes:
  MAX_HOPS       steps out from the starting points (1_meet.cypher)
  EXPLAIN_HOPS   steps on from a finding to the reason behind it (2_explain.cypher)
  and one rule in the queries: never visit the same kind of thing twice on one path.

Pruned — what's worth reporting (the verdict in 1_meet.cypher):
  MIN_SUPPORT    share of the starting points that must share a thing (3 of 5)
  MIN_LIFT       how much more often than chance (2x). Anything at least half of all
                 customers reach (1 / MIN_LIFT) can never get there: that's a hub.

Claude can't change these: the wander tool only takes the starting points. The CLI can,
to show what happens without them.
"""

from __future__ import annotations

import json

MAX_HOPS = 3
EXPLAIN_HOPS = 3
MIN_SUPPORT = 0.6
MIN_LIFT = 2.0
MEMBER_LIMIT = 40   # most "who else" members listed in full

REASON_TEXT = {
    "hub": "most of the population reaches it this way, so sharing it says little",
    "low support": "too few of the starting points reach it",
    "low lift": "enough of the starting points share it, but no more than chance would give (a weak lead)",
}


def check(max_hops: int, explain_hops: int, min_support: float, min_lift: float) -> None:
    if not 1 <= max_hops <= 8:
        raise ValueError("max_hops must be between 1 and 8.")
    if not 1 <= explain_hops <= 5:
        raise ValueError("explain_hops must be between 1 and 5.")
    if not 0 < min_support <= 1:
        raise ValueError("min_support must be between 0 and 1.")
    if min_lift <= 1:
        raise ValueError("min_lift must be above 1 (1 means 'no more than chance').")


def approx_tokens(payload) -> int:
    """Roughly how many tokens this would cost Claude to read (about 4 characters a token)."""
    return len(json.dumps(payload, default=str)) // 4
