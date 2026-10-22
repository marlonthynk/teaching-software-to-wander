"""The wander: start from the things you care about and follow the relationships outwards.

The graph work is in three Cypher files (wander/graph/queries/), run in order:

    1_meet.cypher      walk out from every customer; what do the starting points share,
                       and is it more than chance?  (support, reach, lift, verdict)
    2_explain.cypher   from each finding, walk on to the reason behind it
    3_who_else.cypher  everyone who reaches a finding the same way

This file runs them and does the little that's easier in Python: a thing that's only there
because of another finding (say, the decision behind a queue) is reported as that
finding's explanation, not as a finding of its own. Then it shapes the result for Claude.

Nothing here knows about any particular scenario, queue or customer.
"""

from __future__ import annotations

from collections import defaultdict

from wander import guardrails as g
from wander.graph.db import Graph
from wander.graph.lookups import label_of, kind_of, resolve


def wander(graph: Graph, anchors: list[str], max_hops: int = g.MAX_HOPS,
           explain_hops: int = g.EXPLAIN_HOPS, min_support: float = g.MIN_SUPPORT,
           min_lift: float = g.MIN_LIFT, prune: bool = True) -> dict:
    g.check(max_hops, explain_hops, min_support, min_lift)
    anchors = list(dict.fromkeys(anchors))
    starts = {r["n"]["id"]: r["n"] for r in graph.run("lookups:nodes_by_id", ids=anchors)}
    missing = [a for a in anchors if a not in starts]
    if not anchors or missing:
        raise ValueError(f"Unknown starting point(s): {', '.join(missing) or 'none given'}. "
                         "Use find to look them up.")
    kinds = {kind_of(n) for n in starts.values()}
    if len(kinds) > 1:
        raise ValueError(f"All starting points must be the same kind of thing; got {', '.join(sorted(kinds))}.")
    population = kinds.pop()
    settings = {"max_hops": max_hops, "explain_hops": explain_hops, "min_support": min_support,
                "min_lift": min_lift, "prune": prune}
    anchor_list = [{"id": a, "name": label_of(starts[a]), "type": population} for a in anchors]

    if not prune:
        return _everything(graph, anchors, anchor_list, settings, max_hops)

    # 1. Walk and meet. One row per (thing, route), best first; keep each thing's best route.
    rows = graph.run("1_meet", {"max_hops": max_hops}, anchors=anchors, population=population,
                     min_support=min_support, min_lift=min_lift)
    best: dict[str, dict] = {}
    for r in rows:
        best.setdefault(r["thing"]["id"], dict(r))

    # 2. Explain. Shortest routes first: whatever a finding's explanation reaches (the decision,
    #    the plan, the person who warned about it) is part of that finding, not a finding itself.
    findings, explained = [], set()
    kept = sorted((r for r in best.values() if r["verdict"] == "kept"),
                  key=lambda r: (len(r["route"]), -r["support"], -r["lift"]))
    for r in kept:
        if r["thing"]["id"] in explained:
            continue
        explanation = _explain(graph, r, population, explain_hops)
        explained |= {n for p in explanation for n in p["node_ids"]}
        findings.append((r, explanation))

    # 3. Who else, for each finding.
    convergence = [_finding(graph, r, explanation, anchors, population) for r, explanation in findings]

    pruned = [_pruned(r, len(anchors)) for r in best.values()
              if r["verdict"] != "kept" and r["thing"]["id"] not in explained]
    result = {
        "anchors": anchor_list,
        "settings": settings,
        "summary": _summary(convergence, pruned, len(anchors)),
        "convergence": convergence,
        "pruned": pruned,
        "stats": {
            "anchors": len(anchors),
            "population": f"{rows[0]['population_size'] if rows else '?'} {population}",
            "shared_things": len(best),
            "kept": len(convergence),
            "explained": len(explained),
            "pruned": len(pruned),
        },
    }
    returned = set(anchors) | {c["id"] for c in convergence} | explained
    for c in convergence:
        returned |= {m["id"] for m in c["other_members"]["members"]}
    result["stats"]["nodes_returned"] = len(returned)
    result["stats"]["approx_tokens"] = g.approx_tokens(result)
    return result


def _explain(graph: Graph, row: dict, population: str, explain_hops: int) -> list[dict]:
    came_by = sorted({step.strip("<>") for step in row["route"]})
    records = graph.run("2_explain", {"explain_hops": explain_hops},
                        finding=row["thing"]["id"], came_by=came_by, population=population)
    paths = [[n["id"] for n in r["nodes"]] for r in records]
    out = []
    for r, ids in zip(records, paths):
        if any(other != ids and other[:len(ids)] == ids for other in paths):
            continue  # another path goes further along the same way; that one says it all
        out.append({"path": path_text(r["nodes"], r["rels"]), "node_ids": ids[1:]})
    return out


def _finding(graph: Graph, row: dict, explanation: list, anchors: list[str], population: str) -> dict:
    thing, route = row["thing"], row["route"]
    records = graph.run("3_who_else", {"max_hops": len(route)}, finding=thing["id"], route=route,
                        population=population)
    anchor_paths, members = {}, defaultdict(list)
    route_types = {step.strip("<>") for step in route}
    for r in records:
        customer = r["customer"]
        if customer["id"] in anchors:
            anchor_paths.setdefault(customer["id"], path_text(r["nodes"], r["rels"]))
            continue
        steps = []
        for node, links in zip(r["nodes"][1:-1], r["side_links"]):
            steps.append({"id": node["id"], "type": kind_of(node), "name": label_of(node),
                          **_props(node, without_label=True), **_side_facts(graph, node, links, route_types)})
        members[customer["id"]].append({"via": steps, "edges": [dict(rel) for rel in r["rels"] if dict(rel)]})
    member_list = []
    for cid in sorted(members):
        customer = next(r["customer"] for r in records if r["customer"]["id"] == cid)
        member_list.append({"id": cid, "name": label_of(customer), **_props(customer, without_label=True),
                            "through": members[cid]})
    return {
        "id": thing["id"], "type": kind_of(thing), "name": label_of(thing), "properties": _props(thing),
        "pattern": route_text(route),
        "support": f"{row['support']} of {len(anchors)}", "support_share": round(row["support"] / len(anchors), 2),
        "population_reach": f"{row['reach']} of {row['population_size']}", "lift": round(row["lift"], 2),
        "paths": [anchor_paths[a] for a in anchors if a in anchor_paths],
        "explanation": explanation,
        "other_members": {"count": len(member_list), "breakdown": _breakdown(member_list),
                          "members": member_list[:g.MEMBER_LIMIT], "truncated": len(member_list) > g.MEMBER_LIMIT},
    }


def _side_facts(graph: Graph, node, links: list[dict], route_types: set[str]) -> dict:
    """What else is declared about a thing along the way, including absences ("none")."""
    facts = {}
    for rel in graph.ontology.relationships.values():
        if rel.from_ == kind_of(node) and rel.name not in route_types:
            targets = [l["other"] for l in links if l["type"] == rel.name]
            facts[rel.name.lower()] = ", ".join(targets) or "none"
    return facts


def _breakdown(members: list[dict]) -> dict[str, dict[str, int]]:
    """How many members have each value of the few-valued properties along the way, e.g.
    {"Ticket.status": {"open": 12, "closed": 10}}. Dates, names and free text are left out."""
    seen: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for m in members:
        for t in m["through"]:
            for step in t["via"]:
                for k, v in step.items():
                    if k not in ("id", "type", "name") and isinstance(v, str) and not _is_date(v):
                        seen[f"{step['type']}.{k}"][v].add(m["id"])
    return {key: {v: len(ids) for v, ids in sorted(values.items(), key=lambda kv: (-len(kv[1]), kv[0]))}
            for key, values in sorted(seen.items()) if 1 < len(values) <= 6}


def _pruned(row: dict, n_anchors: int) -> dict:
    thing = row["thing"]
    return {
        "id": thing["id"], "type": kind_of(thing), "name": label_of(thing), "pattern": route_text(row["route"]),
        "support": f"{row['support']} of {n_anchors}", "support_share": round(row["support"] / n_anchors, 2),
        "population_reach": f"{row['reach']} of {row['population_size']}",
        "lift": round(row["lift"], 2), "reason": row["verdict"], "why": g.REASON_TEXT[row["verdict"]],
    }


def _everything(graph: Graph, anchors: list[str], anchor_list: list, settings: dict, max_hops: int) -> dict:
    """No guardrails: every thing reachable, with a path to it. Used to show the cost."""
    names = {a["id"]: a["name"] for a in anchor_list}
    by_thing: dict[str, dict] = {}
    for r in graph.run("everything", {"max_hops": max_hops}, anchors=anchors):
        entry = by_thing.setdefault(r["thing"]["id"], {"node": node_text(r["thing"]), "reached_by": [], "paths": []})
        entry["reached_by"].append(names[r["reached_by"]])
        entry["paths"].append(path_text(r["nodes"], r["rels"]))
    result = {"anchors": anchor_list, "settings": settings,
              "summary": f"No guardrails: every one of {len(by_thing)} things reached, with no judgement of what matters.",
              "nodes": list(by_thing.values()),
              "stats": {"anchors": len(anchors), "nodes_returned": len(by_thing)}}
    result["stats"]["approx_tokens"] = g.approx_tokens(result)
    return result


def _summary(convergence, pruned, n_anchors) -> str:
    weak = [p for p in pruned if p["reason"] == "low lift"]
    if convergence:
        text = (f"Found {len(convergence)} strong common thread(s): " +
                "; ".join(f"{c['type']} {c['name']} ({c['support']} starting points, lift {c['lift']})"
                          for c in convergence) + ".")
    else:
        text = ("No strong common thread found: the only shared things are things most of the "
                "population shares, or that too few of the starting points share.")
    if weak:
        text += " Weak leads, pruned: " + "; ".join(
            f"{p['type']} {p['name']} ({p['support']}, but {p['population_reach']} of the "
            f"population share it, lift {p['lift']})" for p in weak) + "."
    if n_anchors < 5:
        text += f" Only {n_anchors} starting points, so treat any pattern with care."
    return text


# ---------------------------------------------------------------------------
# Base rate: is it more than chance, in plain numbers?


def compare_base_rate(graph: Graph, node: str, since: str | None = None, outcome: str = "churned",
                      population: str = "Customer", max_hops: int = g.MAX_HOPS) -> dict:
    """How often `outcome` happens for customers connected to the node, vs everyone else."""
    thing = resolve(graph, node)
    if since is not None and not _is_date(since):
        raise ValueError("since must be a date like 2026-03-15.")
    field, _, value = outcome.partition("=") if "=" in outcome else ("status", "", outcome)
    rows = {r["connected"]: r for r in graph.run("base_rate", {"max_hops": max_hops}, thing=thing["id"],
                                                 population=population, since=since, field=field, value=value)}
    w, wo = rows.get(True), rows.get(False)
    n_w, k_w = (w["customers"], w["with_outcome"]) if w else (0, 0)
    n_wo, k_wo = (wo["customers"], wo["with_outcome"]) if wo else (0, 0)
    rate_w = k_w / n_w if n_w else 0.0
    rate_wo = k_wo / n_wo if n_wo else 0.0
    name = label_of(thing)
    if not n_w:
        summary = f"No {population.lower()} is connected to {name}" + (f" since {since}." if since else ".")
    else:
        ratio = (f"about {rate_w / rate_wo:.0f}× the rate" if rate_wo and rate_w / rate_wo >= 1.5
                 else "no clear difference" if rate_wo and 0.67 < rate_w / rate_wo < 1.5
                 else "a lower rate" if rate_wo else "against none among the rest")
        summary = (f"Of the {n_w} {population.lower()}s connected to {name}"
                   f"{f' since {since}' if since else ''}, {k_w} have {field} = {value} ({rate_w:.0%}). "
                   f"Of the other {n_wo}, {k_wo} do ({rate_wo:.0%}): {ratio}. This is a signal worth "
                   f"investigating, not proof: it shows an association, not that one caused the other, "
                   f"and the numbers are small.")
    return {"node": {"id": thing["id"], "type": kind_of(thing), "name": name}, "since": since,
            "outcome": f"{field} = {value}",
            "with": {"count": n_w, "outcome": k_w, "rate": round(rate_w, 3)},
            "without": {"count": n_wo, "outcome": k_wo, "rate": round(rate_wo, 3)},
            "summary": summary}


# ---------------------------------------------------------------------------
# Readable text for paths and routes


def route_text(route: list[str]) -> str:
    """['RAISED>', 'ROUTED_TO>'] -> '-[RAISED]-> -[ROUTED_TO]->'."""
    return " ".join(f"<-[{s[1:]}]-" if s.startswith("<") else f"-[{s[:-1]}]->" for s in route)


def node_text(node, detail: bool = True) -> str:
    extras = [f"{k}={v}" for k, v in _props(node).items()
              if v != label_of(node) and len(str(v)) <= 80] if detail else []
    return f"{kind_of(node)}({label_of(node)}{'; ' + ', '.join(extras) if extras else ''})"


def path_text(nodes, rels) -> str:
    """e.g. Customer(Acme) -[RAISED]-> Ticket(...; status=open) -[ROUTED_TO routed_at=...]-> Queue(...)."""
    parts = [node_text(nodes[0], detail=False)]
    for i, rel in enumerate(rels):
        props = ", ".join(f"{k}={_short(v)}" for k, v in sorted(dict(rel).items()))
        inner = f"{rel.type} {props}" if props else rel.type
        forwards = rel.start_node.element_id == nodes[i].element_id
        parts.append(f"-[{inner}]->" if forwards else f"<-[{inner}]-")
        parts.append(node_text(nodes[i + 1]))
    return " ".join(parts)


def _props(node, without_label: bool = False) -> dict:
    skip = {"id", "name", "title"} if without_label else {"id"}
    return {k: v for k, v in sorted(dict(node).items()) if k not in skip}


def _short(value, limit: int = 300) -> str:
    s = str(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _is_date(value) -> bool:
    return isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-" and value[:4].isdigit()
