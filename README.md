# Teaching software to wander

The companion experiment for **[Teaching Software to Wander Like We Do](https://medium.com/)** (Marlon Grech, Medium — link to follow).

A product manager asks: *"Why did these five customers leave?"* In an ordinary store, each customer's record gives a different reason — price, a missing feature, a competitor, building in-house, budget — and there's no pattern. In a graph, software can start from those five customers and **wander** outwards along their relationships, the way a person's mind does, without knowing the path in advance. It finds that all five had support tickets routed to a queue that was retired in a support reorg, which nobody has watched since. Someone even warned about it in a comment on the reorg plan. Twelve more customers have tickets sitting there right now.

This repo holds the same fictional company in two stores — **Records** (SQLite with keyword search) and **Graph** (Neo4j) — and lets you ask Claude the same question against each. The wander is **bounded** (hop limits, a node budget) and **pruned** (it keeps only where the paths converge more than chance would explain). The graph is the map; Claude is the explorer that reads what the wander found and explains it. What the graph can see is set by an **ontology** the business can teach it.

## What you need

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Docker, for Neo4j
- An [Anthropic API key](https://console.anthropic.com/) for the chat app (optional: see [No API key?](#no-api-key) below)

## Set up (about 10 minutes)

```bash
git clone https://github.com/marlonthynk/teaching-software-to-wander.git
```

```bash
cd teaching-software-to-wander
```

```bash
docker compose up -d
```

```bash
uv sync
```

```bash
cp .env.example .env
```

Open `.env` and add your `ANTHROPIC_API_KEY`. Then load the data into both stores:

```bash
uv run python -m wander.cli load
```

And start the chat app:

```bash
uv run chainlit run app.py
```

It opens at http://localhost:8000.

## The chat app

The app has three modes, picked with the **Compare | Records | Graph** switch at the top (the ⓘ next to it explains the difference):

- **Compare** (the default) — every question goes to both agents at once, and the two answers stream in side by side. Under them, a strip compares the work each one did (tool calls, tokens, time), and once both have finished, each answer lists the things in the company it names that the other doesn't ("Only in this answer"). That last part is plain text matching against the names in the data, not another call to Claude.
- **Records** — an ordinary store: records and keyword search. The agent can search, get one record, and list records with simple filters.
- **Graph** — the same data as a graph the agent can wander. The agent calls one `wander` tool; the server does the walking and pruning and hands back a small, explained result.

The two agents never see each other's answers: each keeps its own conversation, in Compare mode too, and a follow-up question goes to both. Switching mode starts a new chat. Each tool call shows up as a step you can open to see what the agent asked for and what came back (Records and Graph also show the raw JSON). Each answer ends with a footer: tool calls, tokens and time.

There's a starter button for each scenario (below). Charlene's question is the first.

## Demo script

1. **Ask both.** The app opens in Compare. Pick *"Why did the five customers who churned in Q3 2026 leave?"*. On the left, Records lists the five customers and their CRM churn reasons; on the right, Graph finds the Integrations queue they all have in common. Compare the "Only in this answer" chips and the work strip underneath.
2. **Open the steps.** In the Graph column, open *What it looked at*, then the `wander from 5 customers…` step: the paths to the Integrations queue, what's behind it (the reorg, the plan, Daniela's comment), the other customers on the same thread, and what was pruned and why. To see one agent on its own with the raw JSON it received, switch to Records or Graph and ask again.
3. **See the raw context**, with no LLM involved:

   ```bash
   uv run python -m wander.cli wander --churned-since 2026-07-01
   ```

4. **The guardrails, before and after.** One hop isn't enough to see anything; no pruning hands Claude the whole graph:

   ```bash
   uv run python -m wander.cli wander --churned-since 2026-07-01 --max-hops 1
   ```

   ```bash
   uv run python -m wander.cli wander --churned-since 2026-07-01 --max-hops 6 --no-prune
   ```

5. **Signal, not proof.**

   ```bash
   uv run python -m wander.cli base-rate "Integrations" --since 2026-03-15
   ```

6. **The business teaches the software.** Open the ontology viewer alongside the chat:

   ```bash
   uv run python -m wander.cli viewer
   ```

   It's at http://localhost:8765. Anyone in the business can teach the software from here, and a developer decides what it actually starts using:

   1. **Propose.** Click **+ Add knowledge**. Add *a kind of thing* ("partner"), then *a connection* (Customer → "referred by" → Partner), each with a sentence on what it means and your name. They appear dashed in the picture: proposed, not yet in use. Nothing in the graph changes, and the Graph agent still can't see them.
   2. **Review.** Open **Review proposals** (http://localhost:8765/review). Each proposal shows who proposed it, whether it's still valid, and how much data it would bring in ("Would load 12 relationships"). Tick the ones to approve, add your name, and click **Apply**. A connection to a proposed kind of thing can only be applied together with it. Rejected proposals are kept, with the reason.
   3. **Ask again.** *"Why are our overdue customers paying late?"* found nothing before; now the Graph agent finds Northwind Consulting, which promised its clients quarterly invoicing. The data was there all along; the software couldn't wander down a path nobody had taught it.

   Try the same with what finance, support and customer success know: *renewal date* on customers (the twelve at-risk customers come back with renewal dates, so you can see who renews first), tickets *escalated to* a person (none of the dead-queue tickets ever were), and a *health score*.

   The chat can't change the ontology: both agents can only read it. Developers can also do all this from the terminal: `ontology propose`, `ontology pending`, `ontology apply --by NAME`, `ontology reject`.

7. **Reset**, so you can run it again:

   ```bash
   uv run python -m wander.cli ontology reset
   ```

### What the CLI shows

`wander --churned-since 2026-07-01` (shortened):

```
Found 1 strong common thread(s): Queue Integrations (5 of 5 starting points, lift 2.48).

CONVERGENCE  Queue Integrations
  5 of 5 starting points reach it (-[RAISED]-> -[ROUTED_TO]->); 27 of 67 of the population do; lift 2.48
  Paths:
    Customer(Redwood Foods) -[RAISED]-> Ticket(Setting up SSO with Okta; created_at=2026-06-03, status=open, topic=question) -[ROUTED_TO routed_at=2026-06-03]-> Queue(Integrations; retired_at=2026-03-15, status=retired)
    …
  Behind it:
    Queue(Integrations) -[RETIRED_BY]-> Decision(Support reorg; date=2026-03-02) -[DOCUMENTED_IN]-> Document(Reorg plan: support teams 2026; type=plan) <-[COMMENTED_ON date=2026-03-04, text=Before we retire the Integrations queue: the routing rule still sends integration tickets there. We need to update it, or they'll go nowhere.]- Person(Daniela; role=Integrations support lead, team=Support)
  Others on the same thread (22):
    Cedar Freight (active): Ticket “Webhooks not firing on record updates” (created_at=2026-08-03, status=open, topic=bug, about=Webhooks); …
    …

PRUNED
  Queue General support — hub: 5 of 5 starting points, 64 of 67 of the population, lift 1.05
  Person Jenny — low support: 2 of 5 starting points, 30 of 67 of the population, lift 0.89
  Feature SSO — low support: 2 of 5 starting points, 9 of 67 of the population, lift 2.98
  …

STATS  population: 67 Customer · shared things: 10 · kept: 1 · explained: 4 · pruned: 8 · nodes returned: 32 · approx tokens: 4035
```

The same run with `--max-hops 6 --no-prune` returns **408 nodes and about 205,000 tokens**, against about 4,000 with the guardrails on. With `--max-hops 1` it finds nothing.

`base-rate "Integrations" --since 2026-03-15`:

```
  with:    5/17 (29%)
  without: 2/50 (4%)

Of the 17 customers that reach Integrations (… since 2026-03-15), 5 have status = churned (29%).
Of the other 50, 2 do (4%): about 7× the rate. This is a signal worth investigating, not proof:
it shows an association, not that one caused the other, and the numbers are small.
```

### A sample chat

One real run of each, with `claude-sonnet-5-5` (shortened; Claude's wording varies from run to run, the context it's given doesn't).

**Records**, after one `list_records` call:

> Five customers churned in Q3 2026 (1 Jul – 30 Sep), and each has a different recorded reason. These come from the `churn_reason` field in the CRM.
>
> | Customer | Churned | Reason |
> |---|---|---|
> | Nimbus Studios | 2026-07-16 | Missing feature |
> | Bluefin Labs | 2026-07-27 | Budget |
> | Redwood Foods | 2026-08-05 | Price |
> | Northstar Media | 2026-09-04 | Building in-house |
> | Vertex Studios | 2026-09-12 | Moved to competitor |
>
> … **No single cause:** the reasons are spread out, so I wouldn't read a pattern into five accounts. … I haven't checked support tickets or notes for these accounts. I can do that if you want.
>
> *Records · 1 tool call · 3,192 input tokens · 730 output tokens · 7s*

**Graph**, after `find`, `view_ontology` and `wander`:

> **Short answer:** The CRM gives a different stated reason for each of the five Q3 2026 churns. However, all five customers also had an open ticket sent to the Integrations queue after it was retired, and that looks like a hidden common factor.
>
> … Each of the five raised a ticket that was routed to the Integrations queue after that queue was retired on 2026-03-15. All five tickets are still open … On 2026-03-04, Daniela (Integrations support lead) commented on the plan: "the routing rule still sends integration tickets there. We need to update it, or they'll go nowhere." … The tickets were routed to the retired queue anyway, which suggests the routing rule was never updated.
>
> **Confidence: Moderate.** … it's about 2.5 times more common among them than among customers overall … I can't tell from the data whether the unanswered tickets caused any of these departures.
>
> **Suggested next steps:** Fix the routing rule and work through the open Integrations tickets. Several active customers have open ones …
>
> *Graph · 3 tool calls · 16,618 input tokens · 1,424 output tokens · 12s*

Both answers are honest about what they saw. Records answered the question it was asked, and offered to dig further. Graph walked to things nobody asked about. Neither called `compare_base_rate` unprompted in these runs; the CLI's `base-rate` command shows what it returns.

## The scenarios

The data is a base company full of ordinary noise (67 customers, ~330 tickets, 4 support queues, 8 product features, 3 decisions, 6 documents, 15 people), plus five planted stories. More than one story, so you can see the wander isn't hard-coded to find one queue, and that it's honest when there's nothing to find.

| # | Question | What the wander should do |
|---|---|---|
| 1 | Why did the five customers who churned in Q3 2026 leave? | Find a hidden common cause: the retired Integrations queue |
| 2 | Why did the customers who upgraded their plan in Q2 2026 upgrade? | Find a different cause on a different path: the feature they'd asked for |
| 3 | Why did the customers who downgraded their plan in Q2 2026 downgrade? | Find nothing, and say so |
| 4 | Why are our overdue customers paying late? | Find nothing, until the ontology learns about partners |
| 5 | Why did the customers who asked for refunds in August 2026 ask for them? | Spot a shared account manager, then prune her as no more than chance |

```bash
uv run python -m wander.cli scenarios
```

```bash
uv run python -m wander.cli wander --scenario coincidence
```

Each scenario is one module in `data/scenarios/` with its question, how to pick its starting points, the story it plants, and an expected outcome that `tests/test_scenarios.py` checks. Adding a sixth means adding one module and one line in `data/scenarios/scenarios.yaml`. The generator (`uv run python -m data.generate`) is deterministic and checks every scenario before it writes anything.

## How the wander works

The graph does the work, in three Cypher queries you can read — and paste into Neo4j Browser — in [`wander/graph/queries/`](wander/graph/queries/):

1. **Walk and meet** — [`1_meet.cypher`](wander/graph/queries/1_meet.cypher). From every customer, follow relationships outwards (up to 3 steps), never visiting the same kind of thing twice on one path — so the walk goes Customer → Ticket → Queue → Decision, but never on to someone else's ticket. For each thing reached, by each route, count how many of the starting points reach it (**support**) and how many of all customers do (**reach**). **Lift** is how much more than chance: the Integrations queue is reached by 5 of the 5, but only 27 of 67 customers — 2.5×. General support is reached by all 5, but by 64 of 67 too — a **hub**, so it says nothing.
2. **Explain** — [`2_explain.cypher`](wander/graph/queries/2_explain.cypher). From a finding, walk on — away from the way the starting points came in — to the reason behind it: the queue was retired by a decision, written up in a plan, which Daniela commented on.
3. **Who else** — [`3_who_else.cypher`](wander/graph/queries/3_who_else.cypher). Everyone else who reaches the finding the same way: the 22 other customers with tickets in that queue, 12 of them still open.

[`wander/graph/wander.py`](wander/graph/wander.py) runs them in order. The only judgement it makes in Python: anything a finding's explanation reaches (the reorg decision) is part of that finding, not a finding of its own. [`base_rate.cypher`](wander/graph/queries/base_rate.cypher) adds the numbers — 29% churn vs 4% — when Claude asks for them.

The server runs these queries, not Claude, so the same question on the same data gives the same context every time. Only Claude's wording varies.

## Is it a fair fight?

It's meant to be.

- **Same data.** Both stores are loaded from the same generated JSON.
- **Same model, same system prompt, same settings, same tool-call limit** (15). The only difference is the toolset. A test checks this.
- **The records store hides nothing.** Ticket rows include their queue, documents include their comments, and the reorg plan with Daniela's comment is searchable. Its tools can list any customer's tickets.
- **Nothing points at the answer.** No prompt or tool description mentions queues, reorgs or the planted pattern.
- **The guardrails aren't Claude's to loosen.** The `wander` tool takes only its starting points; hops, support and lift stay at the server's defaults, so the same starting points always give the same context. (The CLI has the knobs, for the guardrails demo.)

So the Records agent *can* find the dead queue. It has to notice that one queue name turns up for all five customers, among the many tickets every customer has, then think to search for it — and then still think of looking for the twelve at-risk customers and the base rate. If it does, that's a legitimate result. The footer shows how much work it took.

The point isn't that a records store can't answer; it's that it only answers what you think to ask. A store that exposed raw SQL could in principle join its way to the same answer — but only if you already knew which question to ask.

## No API key?

The two toolsets are also available as MCP servers, for Claude Desktop, Claude Code or any MCP client. Register both and ask Charlene's question in **separate conversations**, so one answer can't leak into the other.

**Claude Code:**

```bash
claude mcp add company-records -- uv run --directory "$PWD" python -m wander.mcp.records
```

```bash
claude mcp add company-graph -- uv run --directory "$PWD" python -m wander.mcp.graph
```

**Claude Desktop** (`claude_desktop_config.json`; use your own path):

```json
{
  "mcpServers": {
    "company-records": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/teaching-software-to-wander", "python", "-m", "wander.mcp.records"]
    },
    "company-graph": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/teaching-software-to-wander", "python", "-m", "wander.mcp.graph"]
    }
  }
}
```

The graph server needs Neo4j running. The servers (`wander/mcp/`) are thin wrappers over `wander/tools.py`: the same tools the chat app gives Claude. Only the model and system prompt are now your client's, so the comparison is a little less controlled than in the chat app.

## In Neo4j Browser

Open http://localhost:7474 (user `neo4j`, password from `.env`).

- `queries/wander.cypher` is a hand-written query that draws Charlene's path, for the article's picture. Paste it in and switch to the graph view.
- The wander's own queries are in `wander/graph/queries/`. They take parameters, e.g. run `:param anchors => ['cust_001','cust_021','cust_034','cust_056','cust_059']`, `:param population => 'Customer'`, `:param min_support => 0.6` and `:param min_lift => 2.0`, then paste `1_meet.cypher` with `__MAX_HOPS__` replaced by `3`.

## Tests

They need Neo4j running (`docker compose up -d`), but no API key. Without Neo4j, the graph tests are skipped with a message. They start from the initial ontology and leave Neo4j as your `ontology.yaml` says when they finish.

```bash
uv run pytest
```

## What's where

```
wander/
├── graph/                  Neo4j: the wander, as Cypher        ← start here
│   ├── queries/            1_meet, 2_explain, 3_who_else, base_rate, lookups (.cypher)
│   ├── wander.py           runs the queries in order and shapes the result
│   ├── lookups.py          find, get_details
│   ├── tools.py            the Graph agent's tools
│   └── db.py               the connection; runs a query file, read-only
├── records/                SQLite: the ordinary store
│   ├── store.py            search, get a record, list with filters — plain SQL
│   └── tools.py            the Records agent's tools
├── guardrails.py           hop limits, support and lift thresholds, in one place
├── ontology.py             load and validate the ontology; propose, review, apply
├── proposals.py            the same, with Neo4j reloaded when changes are applied
├── tools.py                both toolsets side by side, for the chat app, MCP and CLI
├── chat/                   the tool-use loop, the shared system prompt, Compare's "only in" chips
├── mcp/                    the optional MCP servers
├── viewer/                 the ontology viewer and its Review page
└── cli.py                  the command line
```

The two stores are separate and each is written the way its database wants to be used: the graph side is Cypher that follows relationships; the records side is plain SQL that answers what you ask. `tools.py` puts their tools side by side for the chat app.

| Elsewhere | What it is |
|---|---|
| `app.py`, `chainlit.md` | The chat app (Chainlit wants them at the root) |
| `public/`, `.chainlit/config.toml` | The chat app's look: logo, avatars, colours, the Compare / Records / Graph switch, and `elements/Compare.jsx` (the side-by-side answers) |
| `ontology.yaml` | The live ontology (`ontology.initial.yaml` is the starting point) |
| `data/generate.py`, `data/scenarios/` | The company and the five planted stories |
| `data/generated/` | The generated data, committed so everyone gets the same |
| `queries/wander.cypher` | A hand-written query that draws Charlene's path in Neo4j Browser |
| `tests/` | The tests: no Docker or API key needed |

## Possible extensions

- Sign-in for the viewer: proposals already wait for a developer's review, but the viewer only listens on localhost and anyone who can open it can also open the Review page. Opening it to a whole organisation would need sign-in, with only developers allowed to apply.
- Causal inference: the base rate is a signal, not proof. That's the next article.
