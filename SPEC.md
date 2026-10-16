# Teaching Software to Wander — build spec

This repo is the companion experiment for the article **"Teaching Software to Wander Like We Do"** (Marlon Grech, Medium). It shows how a graph database lets software *wander* from one thing to the next — the way a human mind does — and why that gives an AI agent context nobody thought to ask for.

This file describes what to build. Build it in the order under [Build order](#build-order), and check each stage against [Acceptance checks](#acceptance-checks) before moving on.

---

## 1. The idea in one paragraph

A normal store answers the question you asked. A graph lets you start from the thing you care about and follow relationships outward, without knowing the path in advance. Wandering on its own is noise, so the wander has to be **bounded** (hop limits, budgets) and **pruned** (keep only where the paths converge). The graph is the **map**; Claude is the **explorer** that reads what the wander found and explains it. The ontology — which entity types and relationships exist — is built **with the business**, and every relationship someone adds is another path the software can wander down.

## 2. The scenario the data must reproduce

A fictional B2B software company. Charlene, a product manager, asks: *"Why did these five customers leave?"* (the five customers who churned in Q3 2026).

- **Flat view:** each churned customer's CRM record gives a different reason — price, a missing feature, moved to a competitor, building in-house, budget. No pattern.
- **Graph view:** all five raised support tickets (about *different* features) that were routed to the **Integrations queue**, which was **retired in the March 2026 support reorg**. Nobody has watched it since. **Daniela**, the integrations support lead, commented on the reorg plan that the routing rule still needed updating.
- **Base rate:** of the **17** customers with tickets routed to that queue since it was retired, **5 have churned (29%)**, versus **2 of the other 50 (4%)**.
- **Forward-looking:** the other **12** of those 17 are still customers, and all have **open tickets** sitting in the dead queue right now.

The wander path the article shows:

```
Customer -[RAISED]-> Ticket -[ROUTED_TO]-> Queue(Integrations) -[RETIRED_BY]-> Decision(Support reorg)
  -[DOCUMENTED_IN]-> Document(Reorg plan) <-[COMMENTED_ON]- Person(Daniela)
Queue(Integrations) <-[ROUTED_TO]- open Ticket <-[RAISED]- 12 other Customers
```

## 3. Architecture

- **Two stores over the same data, so readers can compare:**
  - **Records** — an ordinary store: **SQLite** tables (customers, tickets, documents, people, decisions) with keyword search on top. This is what most teams' setups look like. No Docker needed.
  - **Graph** — **Neo4j 5 Community** in Docker (`docker compose up -d`), with the wander loop.
  - Both are loaded from the **same generated JSON**. Same data, same Claude, same question; the only difference is the store underneath and what that lets the tools do.
- **The main way to run it is a Chainlit chat app** (`chainlit run app.py`). It has two modes — **Records** and **Graph** — chosen per chat; readers ask a question in Records, then switch to Graph and ask it again. Each tool call shows up as a collapsible Chainlit step, so readers can open the wander and see the exact paths and raw context Claude received. Needs an `ANTHROPIC_API_KEY`.
- **Optional MCP servers** for readers without an API key: the same two toolsets exposed over MCP, for Claude Desktop, Claude Code or any MCP client. Thin wrappers — no logic of their own.
- **A CLI** that returns the raw context with no LLM involved, for testing and for the article.
- **Python 3.11+**, managed with `uv`. Libraries: `chainlit`, `anthropic`, `neo4j` (driver), `mcp` (official Python SDK, FastMCP), `pyyaml`, `typer` (CLI), `pytest`. SQLite via the standard library (`sqlite3`, FTS5 for search).
- **The tools are defined once** (`wander/tools.py`) and used by the Chainlit agents, the MCP servers and the CLI alike.
- **The server runs the wander loop, not Claude.** Claude calls one `wander` tool and gets back a small, pruned subgraph with paths. Same question + same data = same context every time. Only Claude's wording varies.

### Repo layout

```
teaching-software-to-wander/
├── README.md                 # what this is, 10-minute setup, running the app, optional MCP, demo script
├── SPEC.md                   # this file
├── app.py                    # Chainlit chat app: Records answer, then Graph answer
├── chainlit.md               # Chainlit welcome screen: what to ask, what to look for
├── docker-compose.yml        # Neo4j 5 community, auth from .env
├── pyproject.toml
├── .env.example              # ANTHROPIC_API_KEY, WANDER_MODEL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
├── ontology.yaml             # the live ontology (source of truth)
├── ontology.initial.yaml     # the starting 7-type ontology, used by `ontology reset`
├── data/
│   ├── generate.py           # builds the base company + applies scenarios, deterministic (seed 42)
│   ├── scenarios/            # one module per planted story + scenarios.yaml (order)
│   ├── generated/            # committed JSON output, incl. scenarios.json manifest
│   ├── load_graph.py         # ontology.yaml + generated JSON → Neo4j
│   └── load_records.py       # generated JSON → SQLite (data/records.db, gitignored)
├── wander/
│   ├── store.py              # GraphStore protocol + Neo4jStore + InMemoryStore
│   ├── records.py            # SQLite records store: search(), get_record()
│   ├── ontology.py           # load/validate/modify ontology.yaml, changelog
│   ├── guardrails.py         # hop limit, node budget, support + lift pruning
│   ├── core.py               # wander(), compare_base_rate(), get_details()
│   ├── tools.py              # tool definitions + handlers for both toolsets (single source)
│   ├── agent.py              # Claude tool-use loop, shared by both agents in the app
│   ├── prompts.py            # the one system prompt both agents share
│   ├── records_server.py     # optional MCP server: the ordinary store
│   ├── graph_server.py       # optional MCP server: the graph
│   └── cli.py                # command-line wrapper over both
├── viewer/
│   └── index.html            # renders the ontology as a picture, refreshes on change
├── queries/
│   └── wander.cypher         # one hand-written, readable Cypher query for the article
└── tests/
    ├── test_data.py          # the planted numbers hold
    ├── test_wander.py        # convergence finds the queue, prunes the noise
    ├── test_scenarios.py     # parametrised over scenarios.json — every scenario's expected outcome
    └── test_ontology.py      # propose/reset/validation, and the "unlock" behaviour
```

### GraphStore abstraction

`core.py` must not talk to Neo4j directly. It uses a small `GraphStore` interface (get node, neighbours along declared relationship types, count population reach for a pattern, etc.). Two implementations:

- `Neo4jStore` — the real one. All reads run in **read transactions** (`session.execute_read`), so the server rejects writes even if a bug tried one. The only write path is `data/load_graph.py` and the ontology reload.
- `InMemoryStore` — loads the same generated JSON. Used by the tests so the logic is testable without Docker, and as a fallback mode for readers who can't run Neo4j (`--store memory`).

## 4. The ontology

`ontology.yaml` is the single source of truth. **The loader only loads node types, properties and relationships that the ontology declares.** Data that exists in `data/generated/` but isn't declared stays invisible to the graph. This is what makes the "the business teaches the software where to look" demo work (section 7).

Each entry carries a plain-English `description` written for a business reader. Format (indicative):

```yaml
entities:
  Customer:
    description: A company that pays us for the product.
    properties: [name, status, plan, churn_reason, churned_at, account_manager]
  ...
relationships:
  RAISED:
    from: Customer
    to: Ticket
    description: The customer opened this support ticket.
  ROUTED_TO:
    from: Ticket
    to: Queue
    properties: [routed_at]
    description: Where the ticket was sent to be handled.
  ...
changelog:
  - {date: 2026-10-16, by: Marlon, change: "Initial ontology"}
```

### Initial ontology (7 entity types)

| Entity | Key properties |
|---|---|
| Customer | name, status (active/churned), plan, churn_reason, churned_at, plan_change (upgrade/downgrade/none), plan_changed_at, payment_status (current/overdue), refund_requested_at |
| Ticket | title, topic, status (open/closed), created_at |
| Queue | name, status (active/retired), retired_at |
| Feature | name, area, released_at |
| Decision | title, date, summary |
| Document | title, type, text |
| Person | name, role, team |

| Relationship | From → To | Properties |
|---|---|---|
| RAISED | Customer → Ticket | |
| ROUTED_TO | Ticket → Queue | routed_at |
| ABOUT | Ticket → Feature | |
| RETIRED_BY | Queue → Decision | |
| DOCUMENTED_IN | Decision → Document | |
| COMMENTED_ON | Person → Document | text, date |
| MANAGES | Person → Customer | |

`ontology.initial.yaml` is a copy of this; `ontology reset` restores it so the demo is repeatable.

## 5. The data (`data/generate.py` + `data/scenarios/`)

Deterministic (seed 42). "Today" in the data is fixed at **2026-10-01** — never use the real clock. Output JSON is committed to `data/generated/` so every reader gets identical data; the generator stays in the repo for transparency.

The data is built in two layers: a **base company** full of realistic noise, then a set of **scenarios** that each plant one story into it. The article uses scenario 1, but the experiment needs more than one story, for two reasons: it proves the wander isn't hard-coded to find one queue, and it shows the wander being honest when there's nothing to find.

### Scale
About **67 customers, ~300 tickets, 4 queues, 8 features, 3 decisions, ~6 documents, ~15 people, 2 partners** (hidden, see scenario 4).

### Queues
- **General support** — used by almost everyone (reach ≥ 55 of 67 customers). This is the hub that must be pruned.
- **Billing** — moderate use.
- **Platform** — moderate use.
- **Integrations** — active until **2026-03-15**, then `status: retired`, `retired_at: 2026-03-15`, `RETIRED_BY` the Support reorg decision. The routing rule was never updated, so integration-type tickets kept landing here after that date and nobody picked them up.

### Base noise
- Every customer has some ordinary tickets in General/Billing/Platform, about a spread of features.
- Every customer is managed by one account manager: **Jenny ~30, Anshit ~20, Andrew ~17** (Jenny's large book matters for scenario 5).
- About **10** customers had Integrations tickets **before** 2026-03-15, all resolved — this gives the date property a reason to exist and keeps the queue from looking suspicious on volume alone.

### Scenarios

#### The scenario framework (so more can be added)
Each scenario is one module in `data/scenarios/` and is listed, in order, in `data/scenarios/scenarios.yaml`. A scenario declares:
- `name`, `title`, and the **question** a user would ask (used as a starter button in the chat app and as a CLI shortcut);
- an **anchor selector** — how to pick the starting nodes (e.g. customers with `churned_at` in Q3 2026);
- a `plant(company, rng)` function that claims the customers it needs from a shared pool and adds the tickets, edges, documents and comments that make the story true;
- an **expected outcome**, machine-checkable: the convergence node it should find (or `none`), the nodes that must be pruned and why, the base-rate numbers, and any **ontology additions required** before it can be found.

Rules:
- Scenarios **claim customers from a pool** so they don't overlap; the generator fails loudly if the pool runs out or two scenarios claim the same customer.
- Scenarios must not change each other's numbers — every scenario's expected outcome is re-checked after **all** scenarios are planted.
- **No scenario-specific code outside `data/scenarios/`.** The wander, guardrails, tools and prompts know nothing about any scenario. A test checks that `wander/` never mentions a scenario name.
- `generate.py` writes `data/generated/scenarios.json` (name, title, question, anchor selector, expected outcome) so tests, the CLI and the chat app can all list scenarios without importing generator code.
- `tests/test_scenarios.py` is **parametrised over `scenarios.json`**: for each scenario it selects the anchors, runs the wander (applying any required ontology additions first, then resetting) and checks the expected outcome. Adding a sixth scenario means adding one module and one line in `scenarios.yaml` — no other code changes.

#### The five starting scenarios

| # | Scenario | Question | What the wander should do |
|---|---|---|---|
| 1 | **The dead queue** | Why did these five customers leave? | Find a hidden common cause |
| 2 | **The feature that sells** | Why did these customers upgrade? | Find a different common cause, on a different path |
| 3 | **No common thread** | Why did these customers downgrade? | Find nothing — and say so |
| 4 | **Hidden until the business teaches it** | Why are these customers paying late? | Find nothing, until someone adds the missing relationship to the ontology |
| 5 | **The coincidence** | Why did these customers ask for refunds? | Spot a shared person, then prune it as no more than chance |

**1. The dead queue (the article's scenario — must hold exactly)**
- Anchors: customers with `churned_at` in Q3 2026 (2026-07-01 to 2026-09-30) — exactly **5**.
- **17 customers** have at least one ticket routed to Integrations **after 2026-03-15**:
  - the **5** Q3 churners. Their CRM `churn_reason` values are all different: "Price", "Missing feature", "Moved to competitor", "Building in-house", "Budget". Their post-March Integrations tickets are each about a **different feature** (e.g. data sync, SSO, API rate limits, webhooks, CSV import). Account managers split 2 / 2 / 1.
  - **12 still active**, each with **at least one open** Integrations ticket created after 2026-03-15, unassigned and untouched.
- Of the **50 other customers**, **2 churned**, both in **H1 2026**, for unrelated reasons. No other scenario may churn a customer.
- Expected: convergence on the **Integrations queue** (lift ≈ 2.5); explanation reaches the Support reorg, the reorg plan and **Daniela's comment**; other members = the 12 at-risk customers; prunes General support (low lift), features and account managers (low support). Base rate with `since=2026-03-15`: **5/17 (29%) vs 2/50 (4%)**.

**2. The feature that sells (a positive story, on a different path)**
- Anchors: customers with `plan_change = upgrade` and `plan_changed_at` in Q2 2026 — **6** customers, none from scenario 1's 17.
- Feature **Advanced reporting** has `released_at: 2026-04-01`. Each of the 6 raised at least one feature-request ticket `ABOUT` Advanced reporting between November 2025 and March 2026, routed to General support or Platform (so the queue is not the thread — the feature is).
- **4 other** active customers also asked for Advanced reporting but haven't upgraded — they're the "other members" (an expansion opportunity, the positive mirror of scenario 1's at-risk list). Few other customers have tickets about this feature at all.
- Expected: convergence on the **Advanced reporting feature** via `RAISED → ABOUT` (high lift, roughly 6/10 vs the population); other members = the 4 who asked but didn't upgrade; the queues they used are pruned as hubs.

**3. No common thread (the control — the wander must find nothing)**
- Anchors: customers with `plan_change = downgrade` and `plan_changed_at` in Q2 2026 — **4** customers.
- Deliberately scattered: different account managers, different queues, different features, no shared decision or document. Their only shared nodes are hubs (General support).
- Expected: **no kept convergence node**. The result must say so plainly ("no strong common thread found — the only shared nodes are things most customers share") and list the pruned hubs with their low lift. This is the honesty check: the graph agent should report that it found no pattern rather than invent one.

**4. Hidden until the business teaches it (ties to the James story and the ontology tools)**
- Anchors: customers with `payment_status = overdue` as of 2026-10-01 — **6** customers.
- Hidden data (generated, **not** in the initial ontology): entity **Partner** (two partners, e.g. "Northwind Consulting" and "Blue Harbour Advisory") and relationship **REFERRED_BY: Customer → Partner**. **5** of the 6 overdue customers were referred by Northwind, which referred **8** customers in total. Northwind's `notes` property records that it promised its clients quarterly invoicing; the company bills monthly. Tom (Head of Partnerships) owns the relationship.
- Through the initial ontology, the 6 overdue customers scatter: different account managers, ordinary tickets.
- Expected **before** the ontology change: no kept convergence node (same honest "nothing found" as scenario 3).
- Expected **after** `propose_change` adds `Partner` and `REFERRED_BY` (as Tom's team would, through the chat): convergence on **Northwind Consulting** (support 5/6, high lift), with its `notes` explaining why; other members = the 3 other Northwind customers who aren't overdue yet.
- This is the strongest demo of the ontology point: the data was there all along, but the software couldn't wander down a path nobody had taught it.

**5. The coincidence (a shared node that isn't a cause)**
- Anchors: customers with `refund_requested_at` in August 2026 — **4** customers.
- **3 of the 4 are managed by Jenny**, 1 by Andrew. Jenny manages ~30 of 67 customers (~45%), so 3 of 4 is about what you'd expect from her book size. Their refund tickets sit in the Billing queue (a moderate hub) and are about different features. No shared decision or document.
- Expected: Jenny reaches the support threshold (0.75) but is **pruned for low lift** (≈1.7, below 2.0), and the result reports her as a **weak lead, pruned** with the numbers, so the agent can say "3 of the 4 are Jenny's customers, but she manages almost half of all customers, so that's likely coincidence — and 4 is a very small sample." No kept convergence node.

### Decisions and documents
- **Support reorg** (2026-03-02) — retires the Integrations queue. `DOCUMENTED_IN` → **Reorg plan** document. **Daniela** (role: Integrations support lead) has a `COMMENTED_ON` edge to the reorg plan, dated 2026-03-04, with text along the lines of: *"Before we retire the Integrations queue, the routing rule still sends integration tickets there — we need to update it or they'll go nowhere."*
- **Pricing update** (2026-01-10) and **New SLA policy** (2026-05-20) — noise decisions with their own documents and a comment or two from other people.

### People
Use these names:
- **Charlene** — Product manager
- **Daniela** — Integrations support lead
- **Tom** — Head of Partnerships
- **Anshit, Andrew, Jenny** — Account managers
- **Dominus** — Head of Customer Success
- **Mike** — CFO
- ~4 support agents and a couple of others (any names)

### Hidden data for the ontology demo (generated, not declared initially)
Generate these in the JSON, but leave them out of `ontology.initial.yaml`:
- **Partner** entity and **REFERRED_BY: Customer → Partner** (partnerships) — see scenario 4.
- **Customer.renewal_date** (finance) — spread across the next 12 months for active customers.
- **ESCALATED_TO: Ticket → Person** (support) — some tickets in General/Billing/Platform were escalated; **no Integrations ticket after 2026-03-15 was ever escalated**.
- **Customer.health_score** (customer success) — 0–100; the 12 at-risk customers skew lower, but not perfectly.

## 6. The wander (`core.wander` + `guardrails.py`)

Signature (indicative):

```python
wander(anchors: list[str], max_hops: int = 5, explain_hops: int = 3,
       min_support: float = 0.6, min_lift: float = 2.0,
       max_nodes: int = 500, prune: bool = True) -> WanderResult
```

### Algorithm
1. **Expand.** Breadth-first from all anchors at once, following only relationship types declared in the ontology, in both directions, up to `max_hops`. Stop expanding when `max_nodes` is reached and set `truncated: true` (the guardrail should be visible, not silent). For every node reached, record **which anchors** reached it and the shortest path from each.
2. **Converge.** A node's **support** is the share of anchors that reach it. Candidate convergence nodes have `support >= min_support` (default: 3 of 5).
3. **Discount hubs (lift).** For each candidate, compute how many of the anchors' population (all nodes with the anchors' label, e.g. all 67 customers) reach it via the **same relationship pattern** the anchors used. `lift = support / (population_reach / population_size)`. Keep candidates with `lift >= min_lift`. Expected: Integrations queue lift ≈ 2.5 (kept); General support ≈ 1.1 (pruned). This is the "keep where the paths converge *more than you'd expect by chance*" rule.
4. **Explain.** From each kept convergence node, walk up to `explain_hops` further and keep the neighbours that aren't hubs (Decision → Document → Person, with edge properties such as Daniela's comment text and dates).
5. **Who else shares the thread.** For each kept convergence node, list the other population nodes that reach it via the same pattern (not anchors), with the properties of the intermediate nodes and edges (e.g. ticket status, routed_at). This is how the 12 at-risk customers surface.
6. **Return** a structured result: anchors, kept convergence nodes (with support, lift, population reach), pruned candidates (name + reason, so the pruning is explainable), explanation subgraph, other members, all **paths as readable hop lists** with edge properties, plus stats (nodes visited, nodes returned, truncated, approximate token size).

With `prune=False`, return everything visited — used to show how big the context gets without guardrails.

### `compare_base_rate`

```python
compare_base_rate(node_id: str, pattern: list[str] | None = None,
                  since: str | None = None, outcome: str = "churned") -> BaseRate
```
Compares the outcome rate for population nodes that reach `node_id` via the pattern (optionally only edges dated on/after `since`) against everyone else. Returns counts, rates, and a one-line plain-English summary. For the Integrations queue with `since="2026-03-15"`: **5/17 (29%) vs 2/50 (4%)**. The summary must say it's a signal, not proof (association, not causation — the article leaves causal inference for a sequel).

### `get_details`
Full properties and immediate edges of one node — so Claude can read a ticket or Daniela's comment in full.

## 7. Ontology tools

`wander/ontology.py` plus graph-toolset tools (used in the chat app and the optional MCP) and CLI subcommands:

- **`view_ontology()`** — the current entity types, properties and relationships, with their business descriptions, in plain language.
- **`propose_change(kind, ..., description, proposed_by)`** — `kind` is `entity`, `property` or `relationship`. Validate (no duplicates, both ends exist, valid names), write to `ontology.yaml`, append to `changelog`, then **reload the affected slice into Neo4j**. The response says how many nodes/edges/properties are now loaded for it — or, if the data source has nothing for it yet, says so clearly ("declared, but no data found yet — someone needs to supply it"). Changes apply immediately; no approval step (keep the demo flowing). Note approval as a possible extension in the README.
- **`ontology reset`** (CLI only, not a tool Claude can call) — restore `ontology.initial.yaml` and reload.

### The "unlock" demo this enables
1. Ask Charlene's question → the five-customer answer plus 12 at-risk customers (unsorted).
2. "In finance we track when each customer renews" → Claude calls `propose_change(kind="property", entity="Customer", name="renewal_date", ...)` → reload.
3. Ask again → the 12 now come back with renewal dates, so they can be sorted by who renews first.
4. Same for `ESCALATED_TO` (support) — reveals none of the dead-queue tickets were ever escalated — and `health_score` (customer success).

### Viewer (`viewer/index.html`)
A single self-contained HTML page (one CDN graph library, e.g. Cytoscape.js) that draws the ontology: entity types as boxes, relationships as labelled arrows, descriptions on hover/click. `python -m wander.cli viewer` serves it on `localhost:8765` with a `/ontology.json` endpoint read live from `ontology.yaml`; the page polls every couple of seconds so a change made through Claude appears on screen. Clean and readable — it will be screenshotted for the article.

## 8. The two toolsets

Both toolsets live in `wander/tools.py` and are used, unchanged, by the Chainlit agents and the optional MCP servers.

### Records toolset (the ordinary store)
Backed by **SQLite** (`data/records.db`, built by `data/load_records.py` from the same generated JSON). One table per record type — customers, tickets, documents, people, decisions — with the fields a normal system would hold: a ticket row has its customer id, title, topic, status, queue name and dates; a customer row has status, plan, churn reason, churned date. Full-text search via SQLite FTS5. The records store holds the **base fields only** (the same as the initial ontology) and is not affected by ontology changes — the unlock demo is a graph feature.

This simulates the typical "records + search" setup most teams have today. It must be a **fair fight, not a rigged one**:
- `search(query, type=None, limit=10)` — keyword search across customers, tickets, documents, people and decisions.
- `get_record(id)` — one record's own fields.
- `list_records(type, filters)` — simple filtered listing (e.g. customers with status churned and churned_at in Q3 2026), so Claude can find Charlene's five without guessing.

No arbitrary SQL, no joins across tables. Nothing is hidden: ticket rows include their queue name, and the reorg plan with Daniela's comment is searchable. If Claude pieces the pattern together anyway, that's a legitimate result — record it honestly. The point the comparison makes is that the ordinary store can only answer what you think to ask; the graph walks to things you didn't know to ask about. The README should say this plainly, including that a store exposing raw SQL could in principle join its way to the answer — but only if you already knew which question to ask.

### Graph toolset
Backed by Neo4j (or `--store memory`). Tools: `wander`, `compare_base_rate`, `get_details`, `find` (look up nodes by name/type/filters, e.g. customers churned since 2026-07-01), `view_ontology`, `propose_change`.

Tool descriptions for both sets: short, clear, same tone, and no hints that steer Claude towards the planted answer. The graph toolset's descriptions explain that `wander` already does the walking and pruning.

## 9. The chat app (`app.py`, Chainlit)

`chainlit run app.py` opens a chat. The welcome screen (`chainlit.md`) explains the experiment in three lines and suggests the flow: ask Charlene's question in **Records**, then switch to **Graph** and ask it again.

### Two modes: Records and Graph
The app has exactly two modes, implemented as **Chainlit chat profiles**: **Records** (default) and **Graph**. There is no "both" mode. Each chat runs in one mode, with one agent, one toolset and one author name on its messages ("Records" or "Graph"), so readers always know which store they're talking to.

- Switching profile starts a **new chat**, so the two modes never share a conversation and one answer can't leak into the other.
- Each agent's tool calls appear as **collapsible Chainlit steps** inside its answer — e.g. "wander from 5 customers (4 hops, 23 nodes kept, 3 candidates pruned)". Opening the step shows the readable paths and the raw context Claude received. These steps are the article's screenshots, so make them clean and readable, not raw JSON by default (JSON available inside, collapsed).
- Each profile has a one-line description in the profile picker: Records — "an ordinary store: records and keyword search"; Graph — "the same data as a graph the agent can wander".

### Fairness rules (non-negotiable)
- **Same model, same system prompt, same settings** in both modes. One shared system prompt in `wander/prompts.py`; the only difference is the tool list.
- **Separate conversations.** Each mode is its own chat, so neither agent ever sees the other's answer.
- The system prompt is neutral: be a helpful analyst for this company, use your tools, say how confident you are, cite what you found. No mention of queues, reorgs or the planted pattern.
- The Graph agent is told to cite the paths `wander` returns and to treat `compare_base_rate` as a signal, not proof.

### Agent loop (`wander/agent.py`)
A plain Anthropic SDK tool-use loop (no agent framework): send messages + tools, run any requested tools via `tools.py`, feed results back, repeat until Claude answers, with a **max of 8 tool calls per answer** (another visible guardrail — if hit, the step says so). Stream the final answer into the Chainlit message. Model from `WANDER_MODEL` in `.env`, defaulting to `claude-sonnet-5-5`; the Chainlit settings panel lets the reader switch model.

### Small UX touches
- The ontology unlock works in chat: "In finance we track when each customer renews" → the Graph agent calls `propose_change`, the step shows what was added and how much data loaded, and the viewer (section 7) updates.
- **Starter buttons, one per scenario**, read from `scenarios.json` (Charlene's question first). Adding a scenario adds a button automatically.

## 10. Optional MCP servers (for readers without an API key)

`python -m wander.records_server` and `python -m wander.graph_server` expose the same two toolsets over MCP (FastMCP), for Claude Desktop, Claude Code or any MCP client. They are thin wrappers over `tools.py` — no logic of their own. Readers register both (e.g. `company-records` and `company-graph`) and ask Charlene's question in **separate conversations** so the answers don't leak into each other. The README covers this as the "no API key" route.

## 11. CLI (`wander/cli.py`)

The CLI returns the **raw context** Claude would receive — for testing without an LLM, and for showing readers exactly what the graph hands over.

```
python -m wander.cli load                               # generate (if needed) + load SQLite and Neo4j
python -m wander.cli scenarios                          # list scenarios and their questions
python -m wander.cli wander --scenario dead-queue       # anchors from a scenario's selector
python -m wander.cli wander --churned-since 2026-07-01  # Charlene's five as anchors
python -m wander.cli wander --churned-since 2026-07-01 --max-hops 1
python -m wander.cli wander --churned-since 2026-07-01 --max-hops 6 --no-prune
python -m wander.cli wander --anchors cust_014,cust_022 --format json
python -m wander.cli base-rate "Integrations" --since 2026-03-15
python -m wander.cli details "Daniela"
python -m wander.cli records search "churn"            # what the Records agent sees
python -m wander.cli records list customers --status churned --since 2026-07-01
python -m wander.cli ontology show | propose ... | reset
python -m wander.cli viewer
```

`--format text` (default) prints readable hop paths like the article; `--format json` prints the full structure. Every `wander` run prints a stats footer: nodes visited, nodes returned, pruned candidates and why, approximate tokens. The `--max-hops 1` and `--no-prune` runs are the guardrails section's before-and-after.

`--store memory` on any command uses `InMemoryStore` instead of Neo4j.

## 12. `queries/wander.cypher`

One hand-written Cypher query that a reader can paste into Neo4j Browser to see Charlene's path drawn as a graph: from the five Q3-churned customers, through their tickets, to the Integrations queue, the reorg decision, the plan document and Daniela's comment. Commented for a non-expert reader. This is for the article's screenshot — the real logic lives in Python.

## 13. README

Written for a reader arriving from the Medium article: what this is (two short paragraphs, linking the article — placeholder link for now), prerequisites, 10-minute setup (`docker compose up -d`, `uv sync`, `cp .env.example .env` and add an Anthropic API key, `python -m wander.cli load`, `chainlit run app.py`), the **no-API-key route** via the optional MCP servers (Claude Desktop config JSON and the Claude Code `claude mcp add` commands for both), and a **demo script**: Charlene's question asked in the Records mode, then again in the Graph mode, opening the wander step, the CLI raw-context view, the guardrails before-and-after, and the ontology unlock with the viewer open alongside. Include a note on fairness (same model and prompt on both sides; the records store hides nothing). British spelling.

## 14. Out of scope

No auth or user accounts, no agent framework (plain SDK loop), no LLM calls outside the chat app, no approval workflow for ontology changes, no causal inference (that's the sequel article), no deployment.

## Build order

1. Repo scaffold: `pyproject.toml`, `docker-compose.yml`, `.env.example`, `.gitignore`.
2. `ontology.yaml` + `ontology.initial.yaml` + `wander/ontology.py` (load/validate).
3. `data/generate.py` + `data/scenarios/` (framework + the five scenarios) → `data/generated/*.json`; `tests/test_data.py` proves the planted numbers.
4. `wander/records.py` + `data/load_records.py` (SQLite) and `wander/store.py` (Neo4j + in-memory) + `data/load_graph.py`.
5. `wander/guardrails.py` + `wander/core.py`; `tests/test_wander.py` and `tests/test_scenarios.py` against `InMemoryStore`.
6. `wander/tools.py` (both toolsets) + `wander/cli.py`.
7. Ontology tools (`propose_change`, reload, reset) + `tests/test_ontology.py`.
8. `wander/prompts.py` + `wander/agent.py` + `app.py` + `chainlit.md` (the chat app).
9. `wander/records_server.py` and `wander/graph_server.py` (optional MCP).
10. `viewer/index.html`.
11. `queries/wander.cypher`, README.
12. End-to-end run against real Neo4j with a real API key; record the CLI outputs and a sample chat transcript in the README demo section.

## Acceptance checks

- `generate.py` is deterministic: two runs produce byte-identical JSON.
- Exactly 5 customers churned in Q3 2026, with 5 different churn reasons; 2 others churned in H1 2026; no other customer churned.
- No customer is claimed by two scenarios, and every scenario's expected outcome still holds after all five are planted.
- `test_scenarios.py` passes for all five: dead queue → Integrations queue; feature that sells → Advanced reporting with 4 other members; no common thread → nothing kept, hubs listed as pruned; hidden until taught → nothing before the ontology change, Northwind after it; coincidence → nothing kept, Jenny reported as a weak lead pruned for low lift.
- Nothing in `wander/` refers to a scenario by name (tested).
- 17 customers have Integrations tickets routed after 2026-03-15; 5 churned, 12 active, each of the 12 with ≥1 open ticket there.
- `wander --churned-since 2026-07-01` returns the **Integrations queue** as the top convergence node; prunes **General support** (low lift), the **features** (low support) and **MANAGES/account managers** (low support), each with a stated reason; the explanation includes the Support reorg decision, the reorg plan and **Daniela's comment**; "other members" includes the 12 at-risk customers with their open tickets.
- The records store and the graph are loaded from the same generated JSON: the same 67 customers, ticket counts and documents are visible through both toolsets.
- The records toolset's `list_records` returns Charlene's five churned customers with their five different churn reasons; nothing in its tools or descriptions points at the Integrations queue.
- In the chat app, the Records and Graph modes use the same model and system prompt (asserted in a test), switching mode starts a new chat, and every tool call appears as a readable Chainlit step.
- The agent loop stops at 8 tool calls per answer and says so.
- The optional MCP servers expose exactly the same tools as the chat app's agents (both import from `tools.py`).
- `base-rate "Integrations" --since 2026-03-15` returns 5/17 (29%) vs 2/50 (4%), worded as a signal, not proof.
- `--no-prune --max-hops 6` returns visibly more nodes/tokens than the default run, and `truncated` is reported if the budget is hit.
- Neo4j reads happen in read transactions only; no tool accepts raw Cypher or SQL.
- Before `propose_change`, `renewal_date` is not visible anywhere through the graph tools; after it, the 12 at-risk customers carry renewal dates. `ontology reset` hides it again.
- Proposing a relationship with no backing data returns the "declared, but no data found yet" message rather than failing.
- All tests pass with `--store memory` and no API key (no Docker needed); the end-to-end run passes against Neo4j.
