// NO GUARDRAILS: everything the starting points can reach in __MAX_HOPS__ steps, with no
// rules at all — through hubs, through other customers, back and forth. One shortest path
// to each thing. This is what an agent would have to read without the wander's pruning,
// and it's only used to show how big that gets (wander --no-prune).

MATCH (a) WHERE a.id IN $anchors
MATCH (a)-[*1..__MAX_HOPS__]-(x)
WITH DISTINCT a, x WHERE x <> a AND NOT x.id IN $anchors
MATCH path = shortestPath((a)-[*..__MAX_HOPS__]-(x))
RETURN x AS thing, a.id AS reached_by, nodes(path) AS nodes, relationships(path) AS rels
ORDER BY x.id, reached_by
