"""A tiny filter language shared by the graph's `find`, the records store and scenario selectors.

    {"status": "churned"}                                  equality
    {"churned_at": {"gte": "2026-07-01", "lte": "2026-09-30"}}  range (ISO dates compare as strings)
    {"plan": {"in": ["Growth", "Enterprise"]}}             one of
"""

from __future__ import annotations

OPERATORS = {"eq", "gte", "lte", "gt", "lt", "in"}


def validate(where: dict | None) -> dict:
    where = where or {}
    if not isinstance(where, dict):
        raise ValueError("Filters must be an object of field: value pairs.")
    for field, cond in where.items():
        if isinstance(cond, dict):
            unknown = set(cond) - OPERATORS
            if unknown:
                raise ValueError(f"Unknown filter operator(s) for {field}: {', '.join(sorted(unknown))}. "
                                 f"Use {', '.join(sorted(OPERATORS))}.")
    return where


def matches(props: dict, where: dict | None) -> bool:
    for field, cond in (where or {}).items():
        value = props.get(field)
        if isinstance(cond, dict):
            for op, target in cond.items():
                if not _check(op, value, target):
                    return False
        elif not _check("eq", value, cond):
            return False
    return True


def _check(op: str, value, target) -> bool:
    if op == "eq":
        return value == target
    if op == "in":
        return value in (target or [])
    if value is None:
        return False
    try:
        if op == "gte":
            return value >= target
        if op == "lte":
            return value <= target
        if op == "gt":
            return value > target
        if op == "lt":
            return value < target
    except TypeError:
        return False
    raise ValueError(f"Unknown filter operator {op}")
