"""Readable text for tool results: what the CLI prints and what the chat app's steps show."""

from __future__ import annotations

import json


def render(tool: str, result: dict) -> str:
    if "error" in result:
        return f"Error: {result['error']}"
    fn = RENDERERS.get(tool)
    return fn(result) if fn else json.dumps(result, indent=2, ensure_ascii=False, default=str)


def wander_text(r: dict) -> str:
    out = []
    names = ", ".join(a["name"] for a in r["anchors"])
    out.append(f"Wander from {len(r['anchors'])} {r['anchors'][0]['type']}: {names}")
    s = r["settings"]
    out.append(f"max_hops={s['max_hops']}  explain_hops={s['explain_hops']}  min_support={s['min_support']}  "
               f"min_lift={s['min_lift']}  prune={s['prune']}")
    out.append("")
    out.append(r["summary"])

    if not s["prune"]:
        out.append("")
        out.append(f"EVERYTHING REACHED ({len(r['nodes'])} nodes)")
        for n in r["nodes"]:
            out.append(f"  {n['node']}  ← {', '.join(n['reached_by'])}")
    for c in r.get("convergence", []):
        out.append("")
        out.append(f"CONVERGENCE  {c['type']} {c['name']}")
        out.append(f"  {c['support']} starting points reach it ({c['pattern']}); "
                   f"{c['population_reach']} of the population do; lift {c['lift']}")
        out.append("  Paths:")
        out += [f"    {p}" for p in c["paths"]]
        if c["explanation"]:
            out.append("  Behind it:")
            out += [f"    {e['path']}" for e in c["explanation"]]
        m = c["other_members"]
        out.append(f"  Others on the same thread ({m['count']}):")
        for key, counts in m.get("breakdown", {}).items():
            out.append(f"    {key}: " + ", ".join(f"{v} {n}" for v, n in counts.items()))
        for member in m["members"]:
            via = "; ".join(_step(st) for t in member["through"] for st in t["via"])
            out.append(f"    {member['name']} ({member.get('status', '')}){': ' + via if via else ''}")
        if m["truncated"]:
            out.append(f"    … and {m['count'] - len(m['members'])} more")
    if r.get("pruned"):
        out.append("")
        out.append("PRUNED")
        for p in r["pruned"]:
            out.append(f"  {p['type']} {p['name']} — {p['reason']}: {p['support']} starting points, "
                       f"{p['population_reach']} of the population, lift {p['lift']}")
    st = r["stats"]
    out.append("")
    out.append("STATS  " + "  ·  ".join(f"{k.replace('_', ' ')}: {v}" for k, v in st.items()))
    return "\n".join(out)


def _step(st: dict) -> str:
    extras = [f"{k}={v}" for k, v in st.items() if k not in ("id", "type", "name") and v is not None]
    return f"{st['type']} “{st['name']}” ({', '.join(extras)})"


def base_rate_text(r: dict) -> str:
    return (f"{r['node']['type']} {r['node']['name']}"
            f"{'  since ' + r['since'] if r['since'] else ''}\n"
            f"  with:    {r['with']['outcome']}/{r['with']['count']} ({r['with']['rate']:.0%})\n"
            f"  without: {r['without']['outcome']}/{r['without']['count']} ({r['without']['rate']:.0%})\n\n"
            f"{r['summary']}")


def details_text(r: dict) -> str:
    out = [f"{r['type']} {r['name']} ({r['id']})"]
    out += [f"  {k}: {v}" for k, v in r["properties"].items()]
    out.append("Connections: " + ", ".join(f"{k} ×{v}" for k, v in r["edge_counts"].items()))
    for e in r["edges"]:
        if "more" in e:
            out.append(f"  … {e['more']} more {e['relationship']}")
            continue
        arrow = f"-[{e['relationship']}]->" if e["direction"] == "out" else f"<-[{e['relationship']}]-"
        extra = {k: v for k, v in e.items() if k not in ("relationship", "direction", "other")}
        out.append(f"  {arrow} {e['other']['type']}({e['other']['name']})"
                   + (f"  {json.dumps(extra, ensure_ascii=False)}" if extra else ""))
    return "\n".join(out)


def search_text(r: dict) -> str:
    if not r["results"]:
        return f"No results for “{r['query']}”."
    return "\n".join(f"{h['id']}  [{h['type']}]  {h['title']}\n    {h['snippet']}" for h in r["results"])


def records_text(r: dict) -> str:
    out = [f"{r['total']} {r['type']} (showing {r['returned']})"]
    for rec in r["records"]:
        out.append("  " + ", ".join(f"{k}={v}" for k, v in rec.items() if k != "text"))
    return "\n".join(out)


def find_text(r: dict) -> str:
    out = [f"{r['total']} found (showing {r['returned']})"]
    for n in r["nodes"]:
        rest = ", ".join(f"{k}={v}" for k, v in n.items() if k not in ("id", "type", "name", "text"))
        out.append(f"  {n['id']}  {n['type']} {n['name']}  {rest}")
    return "\n".join(out)


RENDERERS = {
    "wander": wander_text,
    "compare_base_rate": base_rate_text,
    "get_details": details_text,
    "find": find_text,
    "view_ontology": lambda r: r["ontology"],
    "search": search_text,
    "list_records": records_text,
    "get_record": lambda r: "\n".join(f"{k}: {v}" for k, v in r.items()),
}
