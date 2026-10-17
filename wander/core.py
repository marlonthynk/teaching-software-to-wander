"""The wander: start from the things you care about and follow relationships outward.

The server runs the loop, not Claude. Same question + same data = same context every time.
Nothing here knows about any particular scenario, queue or customer.

    wander()            walk out from the anchors, keep where the paths converge, explain it
    compare_base_rate() how often an outcome happens with a thread vs without it
    get_details()       one node in full, with its immediate edges
    find()              look nodes up by type, filters and name
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from wander import guardrails as g
from wander.stores.graph import GraphStore, Hop, Node, Pattern

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LONG_VALUE = 80        # node property values longer than this are left out of path text
EXPLAIN_LIMIT = 30     # most nodes an explanation may add
MEMBER_LIMIT = 40      # most "other members" listed in full


# ---------------------------------------------------------------------------
# Readable output


def pattern_text(pattern: Pattern) -> str:
    return " ".join(f"-[{rel}]->" if d == ">" else f"<-[{rel}]-" for rel, d in pattern)


def node_text(node: Node, detail: bool = True) -> str:
    if not detail:
        return f"{node.type}({node.label})"
    extras = [f"{k}={v}" for k, v in node.properties.items()
              if k not in ("name", "title") and v is not None and len(str(v)) <= LONG_VALUE]
    return f"{node.type}({node.label}{'; ' + ', '.join(extras) if extras else ''})"


def hop_text(hop: Hop) -> str:
    props = ", ".join(f"{k}={_short(v)}" for k, v in hop.properties.items())
    inner = f"{hop.rel} {props}" if props else hop.rel
    return f"-[{inner}]->" if hop.direction == ">" else f"<-[{inner}]-"


def path_text(path: list, nodes: dict[str, Node], detail_from: int = 1) -> str:
    """[node, hop, node, ...] as 'Customer(A) -[RAISED]-> Ticket(...) -[ROUTED_TO ...]-> Queue(B)'."""
    parts = []
    for i, item in enumerate(path):
        if isinstance(item, Hop):
            parts.append(hop_text(item))
        else:
            parts.append(node_text(nodes[item], detail=i // 2 >= detail_from))
    return " ".join(parts)


def _short(value, limit: int = 300) -> str:
    s = str(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _is_date(value) -> bool:
    return isinstance(value, str) and bool(DATE.match(value))


# ---------------------------------------------------------------------------
# The wander


@dataclass
class Candidate:
    node: str
    pattern: Pattern
    paths: dict[str, list]          # anchor -> example path
    support: float
    reach: int
    reach_share: float
    lift: float
    status: str                     # kept / hub / low support / low lift
    dominated_by: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def support_count(self) -> int:
        return len(self.paths)


class _Nodes(dict):
    """A node cache that fetches what it's missing from the store in one go."""

    def __init__(self, store: GraphStore):
        super().__init__()
        self.store = store

    def ensure(self, ids) -> None:
        missing = [i for i in ids if i not in self]
        if missing:
            self.update(self.store.get_many(missing))


def wander(store: GraphStore, anchors: list[str], max_hops: int = g.DEFAULT_MAX_HOPS,
           explain_hops: int = g.DEFAULT_EXPLAIN_HOPS, min_support: float = g.DEFAULT_MIN_SUPPORT,
           min_lift: float = g.DEFAULT_MIN_LIFT, max_nodes: int = g.DEFAULT_MAX_NODES,
           prune: bool = True) -> dict:
    settings = g.Settings(max_hops, explain_hops, min_support, min_lift, max_nodes, prune)
    anchors = list(dict.fromkeys(anchors))
    if not anchors:
        raise ValueError("Give at least one starting point.")
    nodes = _Nodes(store)
    nodes.ensure(anchors)
    missing = [a for a in anchors if a not in nodes]
    if missing:
        raise ValueError(f"Unknown starting point(s): {', '.join(missing)}. Use find to look them up.")
    types = {nodes[a].type for a in anchors}
    if len(types) > 1:
        raise ValueError(f"All starting points must be the same kind of thing; got {', '.join(sorted(types))}.")
    population = types.pop()
    pop_size = store.count(population)
    anchor_set = set(anchors)

    reach_cache: dict[Pattern, dict[str, set[str]]] = {}

    def reach_of(node_id: str, pattern: Pattern) -> set[str]:
        if pattern not in reach_cache:
            reach_cache[pattern] = store.pattern_reach(population, pattern)
        return reach_cache[pattern].get(node_id, set())

    # 1-2. Expand breadth-first from every anchor at once, not wandering through hubs.
    best: dict[str, dict[str, dict[Pattern, list]]] = {a: {a: {(): [a]}} for a in anchors}
    dist: dict[str, dict[str, int]] = {a: {a: 0} for a in anchors}
    frontier = {a: [(a, (), [a])] for a in anchors}
    visited = set(anchors)
    hubs: dict[str, float] = {}
    not_expanded_population: set[str] = set()
    truncated = False
    for depth in range(1, settings.max_hops + 1):
        expand = sorted({node for a in anchors for node, _, _ in frontier[a]})
        if not expand:
            break
        hops = store.neighbours(expand)
        new_frontier: dict[str, list] = {a: [] for a in anchors}
        for a in anchors:
            for node, pattern, path in frontier[a]:
                for h in hops.get(node, []):
                    known = dist[a].get(h.other)
                    if known is not None and known < depth:
                        continue
                    if h.other not in visited:
                        if len(visited) >= settings.max_nodes:
                            truncated = True
                            continue
                        visited.add(h.other)
                    step = pattern + ((h.rel, h.direction),)
                    entry = best[a].setdefault(h.other, {})
                    if step in entry:
                        continue
                    dist[a][h.other] = depth
                    entry[step] = path + [h, h.other]
                    new_frontier[a].append((h.other, step, entry[step]))
        nodes.ensure({n for a in anchors for n, _, _ in new_frontier[a]})
        if settings.prune and depth < settings.max_hops:
            for a in anchors:
                keep = []
                for node, pattern, path in new_frontier[a]:
                    if nodes[node].type == population:
                        # Don't wander on through other customers: who else shares a thread is step 6.
                        if node not in anchor_set:
                            not_expanded_population.add(node)
                        continue
                    share = len(reach_of(node, pattern)) / pop_size
                    if share >= settings.hub_share:
                        hubs[node] = max(share, hubs.get(node, 0))
                        continue
                    keep.append((node, pattern, path))
                new_frontier[a] = keep
        frontier = new_frontier

    stats = {"anchors": len(anchors), "population": f"{pop_size} {population}",
             "nodes_visited": len(visited), "hubs_not_expanded": len(hubs), "truncated": truncated}

    if not settings.prune:
        return _unpruned_result(anchors, best, nodes, population, settings, stats)

    # 3-4. Converge, and discount by lift. A candidate is a (node, pattern) pair.
    by_key: dict[tuple[str, Pattern], dict[str, list]] = defaultdict(dict)
    for a in anchors:
        for node, patterns in best[a].items():
            if node in anchor_set or nodes[node].type == population:
                continue
            for pattern, path in patterns.items():
                by_key[(node, pattern)][a] = path
    candidates: dict[tuple[str, Pattern], Candidate] = {}
    for (node, pattern), paths in by_key.items():
        if len(paths) < g.MIN_SHARED_ANCHORS:
            continue
        support = len(paths) / len(anchors)
        reach = len(reach_of(node, pattern))
        share = reach / pop_size
        candidates[(node, pattern)] = Candidate(
            node, pattern, paths, support, reach, share, g.lift(support, share),
            g.classify(support, share, settings))

    # 5. Dominance: a node behind another candidate on every path is explanation, not news.
    for key, c in candidates.items():
        c.dominated_by = _dominator(c, candidates)

    best_per_node: dict[str, Candidate] = {}
    for c in candidates.values():
        if c.dominated_by:
            continue
        current = best_per_node.get(c.node)
        rank = (c.status == "kept", c.support, -len(c.pattern), c.lift)
        if current is None or rank > (current.status == "kept", current.support,
                                      -len(current.pattern), current.lift):
            best_per_node[c.node] = c
    kept = sorted((c for c in best_per_node.values() if c.status == "kept"),
                  key=lambda c: (-c.support, -c.lift, c.node))
    pruned = sorted((c for c in best_per_node.values() if c.status != "kept"),
                    key=lambda c: (-c.support, c.status, nodes[c.node].label))

    # 6. Explain each kept node, and list who else shares the thread.
    convergence = []
    for c in kept:
        explanation = _explain(store, nodes, c, population, anchor_set, set(hubs), settings.explain_hops)
        members = _other_members(store, nodes, c, population, anchor_set)
        convergence.append({
            "id": c.node,
            "type": nodes[c.node].type,
            "name": nodes[c.node].label,
            "properties": nodes[c.node].properties,
            "pattern": pattern_text(c.pattern),
            "support": f"{c.support_count} of {len(anchors)}",
            "support_share": round(c.support, 2),
            "population_reach": f"{c.reach} of {pop_size}",
            "lift": round(c.lift, 2),
            "paths": [path_text(c.paths[a], nodes) for a in anchors if a in c.paths],
            "explanation": explanation,
            "other_members": members,
        })

    pruned_out = [{
        "id": c.node, "type": nodes[c.node].type, "name": nodes[c.node].label,
        "pattern": pattern_text(c.pattern), "support": f"{c.support_count} of {len(anchors)}",
        "support_share": round(c.support, 2), "population_reach": f"{c.reach} of {pop_size}",
        "lift": round(c.lift, 2), "reason": c.status, "why": g.REASON_TEXT[c.status],
    } for c in pruned]

    result = {
        "anchors": [{"id": a, "name": nodes[a].label, "type": population} for a in anchors],
        "settings": vars(settings),
        "summary": _summary(convergence, pruned_out, len(anchors)),
        "convergence": convergence,
        "pruned": pruned_out,
        "stats": stats,
    }
    returned = {a for a in anchors} | {c["id"] for c in convergence}
    for c in convergence:
        returned |= {n for p in c["explanation"] for n in p["node_ids"]}
        returned |= {m["id"] for m in c["other_members"]["members"]}
    stats.update({
        "candidates_considered": len(candidates),
        "dominated": sum(1 for c in candidates.values() if c.dominated_by),
        "single_anchor_nodes": sum(1 for v in by_key.values() if len(v) < g.MIN_SHARED_ANCHORS),
        "other_customers_not_expanded": len(not_expanded_population),
        "nodes_returned": len(returned),
    })
    stats["approx_tokens"] = g.approx_tokens(result)
    return result


def _dominator(c: Candidate, candidates: dict) -> str | None:
    """The candidate every one of c's paths passes through first, with at least c's support."""
    found = None
    for path in c.paths.values():
        hit = None
        for i in range(2, len(path) - 1, 2):
            other = candidates.get((path[i], c.pattern[: i // 2]))
            if other is not None and other.support_count >= c.support_count:
                hit = path[i]
                break
        if hit is None:
            return None
        found = found or hit
    return found


def _explain(store, nodes, c: Candidate, population, anchor_set, hubs, explain_hops) -> list[dict]:
    """Walk on from a kept node, away from the path the anchors came in on."""
    used = {rel for rel, _ in c.pattern}
    seen = {c.node} | anchor_set
    paths, frontier = [], [[c.node]]
    for _ in range(explain_hops):
        if not frontier or len(seen) > EXPLAIN_LIMIT:
            break
        hops = store.neighbours(sorted({p[-1] for p in frontier}))
        nodes.ensure({h.other for hs in hops.values() for h in hs if h.rel not in used})
        nxt = []
        for p in frontier:
            for h in hops.get(p[-1], []):
                if h.rel in used or h.other in seen or h.other in hubs:
                    continue
                if nodes[h.other].type == population or len(seen) > EXPLAIN_LIMIT:
                    continue
                seen.add(h.other)
                nxt.append(p + [h, h.other])
        paths += nxt
        frontier = nxt
    # only report maximal paths (a path that another one extends adds nothing)
    ends = {id(p): p for p in paths}
    maximal = [p for p in paths if not any(q is not p and q[: len(p)] == p for q in ends.values())]
    return [{"path": path_text(p, nodes), "node_ids": [x for x in p if not isinstance(x, Hop)]}
            for p in maximal]


def _other_members(store, nodes, c: Candidate, population, anchor_set) -> dict:
    """Everyone else in the population who reaches the kept node the same way."""
    paths = [p for p in store.pattern_paths(population, c.pattern, c.node) if p[0] not in anchor_set]
    paths.sort(key=lambda p: [x for x in p if not isinstance(x, Hop)])  # stores return paths in any order
    by_member: dict[str, list] = defaultdict(list)
    for p in paths:
        by_member[p[0]].append(p)
    nodes.ensure(set(by_member) | {x for p in paths for x in p if not isinstance(x, Hop)})
    # For things along the way (e.g. tickets), say what else is declared about them, including
    # absences: "escalated_to: none" is information a walk alone can't show.
    middle = sorted({x for p in paths for x in p[2:-1:2]})
    side = store.neighbours(middle) if middle else {}
    used = {rel for rel, _ in c.pattern}
    onto = store.ontology
    members = []
    for m in sorted(by_member):
        through = []
        for p in by_member[m]:
            steps = []
            for x in p[2:-1:2]:
                node = nodes[x]
                facts = {}
                for rel in onto.relationships.values():
                    if rel.from_ == node.type and rel.name not in used:
                        targets = [h.other for h in side.get(x, []) if h.rel == rel.name and h.direction == ">"]
                        nodes.ensure(targets)
                        facts[rel.name.lower()] = ", ".join(nodes[t].label for t in targets) or "none"
                props = {k: v for k, v in node.properties.items() if v != node.label}
                steps.append({"id": x, "type": node.type, "name": node.label, **props, **facts})
            edges = [h.properties for h in p if isinstance(h, Hop) and h.properties]
            through.append({"via": steps, "edges": edges})
        members.append({"id": m, "name": nodes[m].label, **nodes[m].properties, "through": through})
    return {"count": len(members), "breakdown": _breakdown(members), "members": members[:MEMBER_LIMIT],
            "truncated": len(members) > MEMBER_LIMIT}


def _breakdown(members: list[dict]) -> dict[str, dict[str, int]]:
    """How many members have each value of the few-valued properties along the way.

    e.g. {"Ticket.status": {"open": 12, "closed": 10}}: a member with one open and one
    closed ticket counts in both. Dates, names and free text are left out.
    """
    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for m in members:
        for t in m["through"]:
            for step in t["via"]:
                for k, v in step.items():
                    if k in ("id", "type", "name") or not isinstance(v, str) or _is_date(v):
                        continue
                    seen[f"{step['type']}.{k}"][v].add(m["id"])
    return {key: {v: len(ids) for v, ids in sorted(values.items(), key=lambda kv: (-len(kv[1]), kv[0]))}
            for key, values in sorted(seen.items())
            if 1 < len(values) <= 6}


def _summary(convergence, pruned, n_anchors) -> str:
    weak = [p for p in pruned if p["reason"] == "low lift"]
    if convergence:
        parts = [f"{c['type']} {c['name']} ({c['support']} starting points, lift {c['lift']})"
                 for c in convergence]
        text = f"Found {len(convergence)} strong common thread(s): " + "; ".join(parts) + "."
    else:
        text = ("No strong common thread found: the only shared nodes are things most of the "
                "population shares, or that too few of the starting points share.")
    if weak:
        text += " Weak leads, pruned: " + "; ".join(
            f"{p['type']} {p['name']} ({p['support']}, but {p['population_reach']} of the population "
            f"share it, lift {p['lift']})" for p in weak) + "."
    if n_anchors < 5:
        text += f" Only {n_anchors} starting points, so treat any pattern with care."
    return text


def _unpruned_result(anchors, best, nodes, population, settings, stats) -> dict:
    """Everything the walk touched, with one path per node: what context looks like with no guardrails."""
    everything = {}
    for a in anchors:
        for node, patterns in best[a].items():
            if node == a:
                continue
            pattern, path = min(patterns.items(), key=lambda kv: (len(kv[0]), kv[0]))
            everything.setdefault(node, {"node": node_text(nodes[node]), "reached_by": [], "paths": []})
            everything[node]["reached_by"].append(nodes[a].label)
            everything[node]["paths"].append(path_text(path, nodes))
    result = {
        "anchors": [{"id": a, "name": nodes[a].label, "type": population} for a in anchors],
        "settings": vars(settings),
        "summary": f"Unpruned: every one of {len(everything)} nodes reached, with no convergence or lift.",
        "nodes": [everything[k] for k in sorted(everything)],
        "stats": stats,
    }
    stats["nodes_returned"] = len(everything)
    stats["approx_tokens"] = g.approx_tokens(result)
    return result


# ---------------------------------------------------------------------------
# Base rate


def type_pattern(store: GraphStore, from_type: str, to_type: str) -> Pattern:
    """The shortest chain of declared relationships from one entity type to another."""
    if from_type == to_type:
        return ()
    rels = store.ontology.relationships.values()
    frontier, seen = [(from_type, ())], {from_type}
    while frontier:
        nxt = []
        for t, pattern in frontier:
            for r in rels:
                for here, there, d in ((r.from_, r.to, ">"), (r.to, r.from_, "<")):
                    if here == t and there not in seen:
                        step = pattern + ((r.name, d),)
                        if there == to_type:
                            return step
                        seen.add(there)
                        nxt.append((there, step))
        frontier = nxt
    raise ValueError(f"Nothing in the ontology connects {from_type} to {to_type}.")


def parse_pattern(text: str | list) -> Pattern:
    """'RAISED> ROUTED_TO>' or ['RAISED>', 'ROUTED_TO>'] or the arrow form from wander output."""
    if isinstance(text, str):
        text = re.findall(r"<-\[([A-Z0-9_]+)\]-|-\[([A-Z0-9_]+)\]->|([A-Z0-9_]+)([<>])", text)
        steps = []
        for back, fwd, rel, d in text:
            steps.append((back, "<") if back else (fwd, ">") if fwd else (rel, d))
        return tuple(steps)
    out = []
    for s in text:
        if not s or s[-1] not in "<>":
            raise ValueError(f"Pattern step {s!r} must end in > (forwards) or < (backwards).")
        out.append((s[:-1], s[-1]))
    return tuple(out)


def resolve(store: GraphStore, ref: str) -> Node:
    """A node by id, or by (unique, case-insensitive) name."""
    node = store.get(ref)
    if node:
        return node
    hits = store.find(name=ref, limit=50)
    exact = [n for n in hits if n.label.lower() == ref.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"Nothing called {ref!r}. Use find to look it up.")
    raise ValueError(f"{ref!r} matches several things: " + ", ".join(f"{n.type} {n.label} ({n.id})" for n in hits[:10]))


def compare_base_rate(store: GraphStore, node_id: str, pattern=None, since: str | None = None,
                      outcome: str = "churned", population: str = "Customer") -> dict:
    """How often `outcome` happens for population nodes that reach the node, vs everyone else."""
    target = resolve(store, node_id)
    pattern = parse_pattern(pattern) if pattern else type_pattern(store, population, target.type)
    for rel, _ in pattern:
        if rel not in store.ontology.relationships:
            raise ValueError(f"{rel} isn't a declared relationship.")
    if since is not None and not _is_date(since):
        raise ValueError("since must be a date like 2026-03-15.")
    field_, _, value = outcome.partition("=") if "=" in outcome else ("status", "", outcome)

    paths = store.pattern_paths(population, pattern, target.id)
    if since:
        paths = [p for p in paths if _dated_on_or_after(p, since, store)]
    with_thread = {p[0] for p in paths}
    everyone = {n.id: n for n in store.find(type_=population, limit=100000)}
    without = set(everyone) - with_thread

    def count(ids):
        return sum(1 for i in ids if str(everyone[i].properties.get(field_)) == value)

    w, wo = count(with_thread), count(without)
    rate_w = w / len(with_thread) if with_thread else 0.0
    rate_wo = wo / len(without) if without else 0.0
    how = f"{pattern_text(pattern)} {target.type}({target.label})" + (f" since {since}" if since else "")
    if not with_thread:
        summary = f"No {population.lower()} reaches {target.label} that way" + (f" since {since}." if since else ".")
    else:
        ratio = (f"about {rate_w / rate_wo:.0f}× the rate" if rate_wo and rate_w / rate_wo >= 1.5
                 else "no clear difference" if rate_wo and 0.67 < rate_w / rate_wo < 1.5
                 else "a lower rate" if rate_wo else "against none among the rest")
        summary = (f"Of the {len(with_thread)} {population.lower()}s that reach {target.label} "
                   f"({how}), {w} have {field_} = {value} ({rate_w:.0%}). Of the other {len(without)}, "
                   f"{wo} do ({rate_wo:.0%}): {ratio}. This is a signal worth investigating, not proof: "
                   f"it shows an association, not that one caused the other, and the numbers are small.")
    return {
        "node": {"id": target.id, "type": target.type, "name": target.label},
        "pattern": pattern_text(pattern), "since": since, "outcome": f"{field_} = {value}",
        "with": {"count": len(with_thread), "outcome": w, "rate": round(rate_w, 3)},
        "without": {"count": len(without), "outcome": wo, "rate": round(rate_wo, 3)},
        "summary": summary,
    }


def _dated_on_or_after(path: list, since: str, store: GraphStore) -> bool:
    dates = [v for h in path if isinstance(h, Hop) for v in h.properties.values() if _is_date(v)]
    if not dates:  # no dated edges on the way: fall back to dates on the nodes in between
        middle = store.get_many([x for x in path[2:-1:2]])
        dates = [v for n in middle.values() for v in n.properties.values() if _is_date(v)]
    return bool(dates) and all(d >= since for d in dates)


# ---------------------------------------------------------------------------
# Details and lookup


def get_details(store: GraphStore, ref: str, edge_limit: int = 40) -> dict:
    node = resolve(store, ref)
    hops = store.neighbours([node.id])[node.id]
    others = store.get_many(sorted({h.other for h in hops}))
    by_rel: dict[str, list] = defaultdict(list)
    for h in sorted(hops, key=lambda h: (h.rel, h.direction, h.other)):
        by_rel[f"{h.rel}{h.direction}"].append(h)
    edges = []
    for key, hs in by_rel.items():
        for h in hs[:edge_limit]:
            o = others[h.other]
            edges.append({"relationship": h.rel, "direction": "out" if h.direction == ">" else "in",
                          "other": {"id": o.id, "type": o.type, "name": o.label}, **h.properties})
        if len(hs) > edge_limit:
            edges.append({"relationship": hs[0].rel, "more": len(hs) - edge_limit})
    return {"id": node.id, "type": node.type, "name": node.label, "properties": node.properties,
            "edge_counts": {k: len(v) for k, v in by_rel.items()}, "edges": edges}


def find(store: GraphStore, type_: str | None = None, where: dict | None = None,
         name: str | None = None, limit: int = 50) -> dict:
    if type_ is not None and type_ not in store.ontology.entities:
        raise ValueError(f"{type_} isn't a declared entity type. Declared: {', '.join(store.ontology.entities)}.")
    hits = store.find(type_=type_, where=where, name=name, limit=10000)
    limit = max(1, min(int(limit), 200))
    return {"total": len(hits), "returned": min(limit, len(hits)),
            "nodes": [{"id": n.id, "type": n.type, "name": n.label, **n.properties} for n in hits[:limit]]}
