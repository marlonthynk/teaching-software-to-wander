// LOOKUPS used by the find, get_details and compare_base_rate tools. Each block below is one
// query, picked out by its name line.

// name: nodes_by_id
MATCH (n) WHERE n.id IN $ids
RETURN n;

// name: find
// Nodes of one kind (or any kind), optionally whose name or title contains $name.
// Filters on properties are applied afterwards in Python (wander/filters.py), so nothing a
// user types ever becomes part of a query.
MATCH (n)
WHERE ($kind IS NULL OR $kind IN labels(n))
  AND ($name IS NULL OR toLower(coalesce(n.name, n.title, '')) CONTAINS toLower($name))
RETURN n
ORDER BY n.id;

// name: resolve
// A node by its id, or by its name or title.
MATCH (n)
WHERE n.id = $ref
   OR toLower(coalesce(n.name, n.title, '')) = toLower($ref)
   OR toLower(coalesce(n.name, n.title, '')) CONTAINS toLower($ref)
RETURN n, n.id = $ref OR toLower(coalesce(n.name, n.title, '')) = toLower($ref) AS exact
ORDER BY exact DESC, n.id
LIMIT 10;

// name: details
// One node and every relationship it has, with the thing at the other end.
MATCH (n {id: $id})
OPTIONAL MATCH (n)-[r]-(other)
RETURN n, type(r) AS rel, startNode(r) = n AS outgoing, properties(r) AS props, other
ORDER BY rel, outgoing DESC, other.id;

// name: count
MATCH (n) WHERE $population IN labels(n)
RETURN count(n) AS n;
