// BASE RATE: how often does an outcome happen for customers connected to this thing,
// against everyone else? A signal worth investigating, not proof.
//
// "Connected" means a path of up to __MAX_HOPS__ steps that never visits the same kind of
// thing twice (the same rule as the walk). With $since, every date on the path's
// relationships (e.g. when a ticket was routed) must be on or after it.
//
// Parameters: $thing (an id), $population (e.g. 'Customer'), $since (a date or null),
// $field and $value (the outcome, e.g. status = 'churned').

MATCH (thing {id: $thing})
MATCH (c) WHERE $population IN labels(c)
OPTIONAL MATCH path = (c)-[*1..__MAX_HOPS__]-(thing)
WHERE all(i IN range(1, size(nodes(path)) - 1)
          WHERE NOT labels(nodes(path)[i])[0] IN [n IN nodes(path)[0..i] | labels(n)[0]])
  AND ($since IS NULL OR all(r IN relationships(path) WHERE
        all(k IN keys(r) WHERE NOT (k ENDS WITH '_at' OR k = 'date') OR r[k] >= $since)))
WITH c, count(path) > 0 AS connected
RETURN connected,
       count(c) AS customers,
       sum(CASE WHEN toString(c[$field]) = $value THEN 1 ELSE 0 END) AS with_outcome
ORDER BY connected DESC
