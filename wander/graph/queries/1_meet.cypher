// STEP 1 — WALK AND MEET: what do the starting points share, and is it more than chance?
//
// Start from EVERY customer (the whole population) and follow relationships outwards,
// up to __MAX_HOPS__ steps, in any direction. One rule keeps the walk on track: never visit
// the same kind of thing twice on one path. So a walk can go
//     Customer -> Ticket -> Queue -> Decision
// but never Customer -> Ticket -> Queue -> (someone else's) Ticket.
//
// For every thing reached, by every route, count:
//   support = how many of the starting points reach it this way
//   reach   = how many of ALL customers reach it this way
//   lift    = support share / reach share   (1.0 = no more than chance)
//
// Then give each a verdict:
//   hub          most customers reach it this way, so sharing it says nothing
//   low support  too few of the starting points share it
//   low lift     enough of them share it, but no more than chance would give (a weak lead)
//   kept         shared, and more than chance: worth explaining
//
// Parameters: $anchors (the starting points' ids), $population (their label, e.g. 'Customer'),
// $min_support, $min_lift. Cypher can't take the hop limit as a parameter, so wander.py
// writes it in place of __MAX_HOPS__ (to run this by hand, replace it with e.g. 3).

MATCH (c) WHERE $population IN labels(c)
WITH collect(c) AS everyone
UNWIND everyone AS c
MATCH path = (c)-[*1..__MAX_HOPS__]-(thing)
WITH size(everyone) AS population_size, c, thing, path,
     [n IN nodes(path) | labels(n)[0]] AS kinds

// never the same kind of thing twice on one path
WHERE all(i IN range(1, size(kinds) - 1) WHERE NOT kinds[i] IN kinds[0..i])

// the route, e.g. ['RAISED>', 'ROUTED_TO>'] or ['<MANAGES']: '>' follows the relationship's
// direction, '<' walks it backwards
WITH population_size, c, thing,
     [i IN range(0, length(path) - 1) |
        CASE WHEN startNode(relationships(path)[i]) = nodes(path)[i]
             THEN type(relationships(path)[i]) + '>'
             ELSE '<' + type(relationships(path)[i]) END] AS route

WITH population_size, thing, route,
     count(DISTINCT c) AS reach,
     count(DISTINCT CASE WHEN c.id IN $anchors THEN c END) AS support
WHERE support >= 2

WITH thing, route, support, reach, population_size,
     toFloat(support) / size($anchors) AS support_share,
     toFloat(reach) / population_size AS reach_share
RETURN thing, route, support, reach, population_size,
       support_share / reach_share AS lift,
       CASE
         WHEN reach_share >= 1.0 / $min_lift THEN 'hub'
         WHEN support_share < $min_support THEN 'low support'
         WHEN support_share / reach_share < $min_lift THEN 'low lift'
         ELSE 'kept'
       END AS verdict
ORDER BY verdict = 'kept' DESC, support DESC, lift DESC, size(route)
