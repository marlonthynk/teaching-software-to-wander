"""Compare mode's "only in one answer" chips: which things in the company each answer names.

No extra call to Claude. Every named thing in the data (a queue, a person, a decision, a
customer...) is looked for in each answer's text, and what only one answer mentions is
shown under it. Tickets are left out: their titles are sentences, not names.

A single-word name ("Billing", "Tom") has to match its case, so the word used in passing
("billing") doesn't count; a longer one ("Pricing update") matches any case.
"""

from __future__ import annotations

import re
from functools import cache

from data.source import read_generated


@cache
def names_of_things() -> tuple[tuple[str, str], ...]:
    """(name, kind) for every named thing in the company data, except tickets."""
    nodes, _ = read_generated()
    found = {}
    for n in nodes:
        if n["type"] == "Ticket":
            continue
        name = n["properties"].get("name") or n["properties"].get("title")
        if name:
            found.setdefault(name, n["type"])
    return tuple(found.items())


def mentioned(text: str, names=None) -> list[dict]:
    """The things named in `text`, in the order of the data."""
    hits = []
    for name, kind in names or names_of_things():
        flags = 0 if " " not in name else re.IGNORECASE
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags):
            hits.append({"name": name, "kind": kind})
    return hits


def only_in(texts: dict[str, str], names=None) -> dict[str, list[dict]]:
    """For each answer, the things it names that no other answer does."""
    found = {side: mentioned(text, names) for side, text in texts.items()}
    return {side: [h for h in hits if not any(h in found[o] for o in found if o != side)]
            for side, hits in found.items()}
