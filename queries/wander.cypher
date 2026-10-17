// Charlene's question, drawn as a graph.
//
// Paste this into Neo4j Browser (http://localhost:7474, after `docker compose up -d` and
// `uv run python -m wander.cli load`) and switch to the graph view.
//
// This is the path the wander found, written out by hand so you can see it. The real
// logic (walking out without knowing the path in advance, then pruning) lives in
// wander/core.py. Here we already know where to look.

// 1. Start from the five customers who left between July and September 2026.
MATCH (customer:Customer)
WHERE customer.churned_at >= '2026-07-01' AND customer.churned_at <= '2026-09-30'

// 2. Follow each one to the support tickets they raised, and on to the queue each
//    ticket was routed to. Only keep queues that have been retired.
MATCH (customer)-[raised:RAISED]->(ticket:Ticket)-[routed:ROUTED_TO]->(queue:Queue)
WHERE queue.status = 'retired'

// 3. From the queue, follow the decision that retired it, the document that wrote the
//    decision up, and the people who commented on that document.
MATCH (queue)-[retired:RETIRED_BY]->(decision:Decision)-[documented:DOCUMENTED_IN]->(doc:Document)
OPTIONAL MATCH (person:Person)-[comment:COMMENTED_ON]->(doc)

// 4. Return the paths, so Neo4j Browser draws them. Click Daniela's COMMENTED_ON
//    relationship to read what she wrote.
RETURN customer, raised, ticket, routed, queue, retired, decision, documented, doc, person, comment;
