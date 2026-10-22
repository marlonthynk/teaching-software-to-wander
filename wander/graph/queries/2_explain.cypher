// STEP 2 — EXPLAIN: from a finding, keep walking to the reason behind it.
//
// Walk on from the finding up to __EXPLAIN_HOPS__ more steps, but AWAY from the way the
// starting points came in ($came_by: the relationship types on their route), and without
// stepping onto any customer. For a support queue, that might be:
//     Queue -[RETIRED_BY]-> Decision -[DOCUMENTED_IN]-> Document <-[COMMENTED_ON]- Person
// and not back out through other customers' tickets.
//
// The same rule as the walk applies: never the same kind of thing twice on one path.
//
// Parameters: $finding (the finding's id), $came_by (relationship types to avoid),
// $population (e.g. 'Customer'). __EXPLAIN_HOPS__ is written in by wander.py.

MATCH path = (finding {id: $finding})-[*1..__EXPLAIN_HOPS__]-(next)
WHERE none(r IN relationships(path) WHERE type(r) IN $came_by)
  AND none(n IN nodes(path) WHERE $population IN labels(n))
WITH path, [n IN nodes(path) | labels(n)[0]] AS kinds
WHERE all(i IN range(1, size(kinds) - 1) WHERE NOT kinds[i] IN kinds[0..i])
RETURN nodes(path) AS nodes, relationships(path) AS rels
ORDER BY length(path) DESC
