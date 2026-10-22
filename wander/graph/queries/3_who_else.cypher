// STEP 3 — WHO ELSE: every customer who reaches the finding by the same route.
//
// The starting points' own paths (the evidence for the finding), and everyone else on the
// same thread — e.g. other customers whose tickets went the same way.
// For each thing along the way (e.g. a ticket) it also lists that thing's other
// connections, so an absence shows too ("escalated to: nobody").
//
// The route is worked out exactly as in 1_meet.cypher, and must equal $route.
// Parameters: $finding, $route (e.g. ['RAISED>', 'ROUTED_TO>']), $population.
// __MAX_HOPS__ is written in by wander.py (it's the route's length).

MATCH path = (c)-[*__MAX_HOPS__]-(finding {id: $finding})
WHERE $population IN labels(c)
WITH c, path, [n IN nodes(path) | labels(n)[0]] AS kinds
WHERE all(i IN range(1, size(kinds) - 1) WHERE NOT kinds[i] IN kinds[0..i])
  AND [i IN range(0, length(path) - 1) |
        CASE WHEN startNode(relationships(path)[i]) = nodes(path)[i]
             THEN type(relationships(path)[i]) + '>'
             ELSE '<' + type(relationships(path)[i]) END] = $route
RETURN c AS customer, nodes(path) AS nodes, relationships(path) AS rels,
       [n IN nodes(path)[1..-1] | [(n)-[r]->(other) | {type: type(r), other: coalesce(other.name, other.title, other.id)}]]
         AS side_links
ORDER BY c.id
