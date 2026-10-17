# Teaching software to wander

The companion experiment for **[Teaching Software to Wander Like We Do](https://medium.com/)** (Marlon Grech, Medium — link to follow).

A product manager asks: *"Why did these five customers leave?"* In an ordinary store, each customer's record gives a different reason — price, a missing feature, a competitor, building in-house, budget — and there's no pattern. In a graph, software can start from those five customers and **wander** outwards along their relationships, the way a person's mind does, without knowing the path in advance. It finds that all five had support tickets routed to a queue that was retired in a support reorg, which nobody has watched since. Someone even warned about it in a comment on the reorg plan. Twelve more customers have tickets sitting there right now.

This repo holds the same fictional company in two stores — **Records** (SQLite with keyword search) and **Graph** (Neo4j) — and lets you ask Claude the same question against each. The wander is **bounded** (hop limits, a node budget) and **pruned** (it keeps only where the paths converge more than chance would explain). The graph is the map; Claude is the explorer that reads what the wander found and explains it. What the graph can see is set by an **ontology** the business can teach it.

## What you need

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Docker, for Neo4j (optional: everything also runs with `--store memory`)
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

No Docker? Skip `docker compose up -d`, set `WANDER_STORE=memory` in `.env`, and run `uv run python -m wander.cli load --store memory`. The graph is then held in memory, loaded from the same JSON.

## The chat app

The app has two modes, picked with the **Records | Graph** switch at the top (the ⓘ next to it explains the difference):

- **Records** — an ordinary store: records and keyword search. The agent can search, get one record, and list records with simple filters.
- **Graph** (the default) — the same data as a graph the agent can wander. The agent calls one `wander` tool; the server does the walking and pruning and hands back a small, explained result.

Switching mode starts a new chat, so neither agent ever sees the other's answer. Each tool call shows up as a step you can open to see exactly what the agent asked for and the raw context it got back. Each answer ends with a footer: tool calls, tokens and time.

There's a starter button for each scenario (below). Charlene's question is the first.

## Demo script

1. **Ask in Records.** The app opens in Graph, so switch to Records at the top first. Pick *"Why did the five customers who churned in Q3 2026 leave?"*. Watch it list the five customers and their CRM churn reasons. Open the steps.
2. **Ask in Graph.** Switch back to Graph and ask again. Open the `wander from 5 customers…` step: the paths to the Integrations queue, what's behind it (the reorg, the plan, Daniela's comment), the other customers on the same thread, and what was pruned and why.
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

STATS  nodes visited: 196 · hubs not expanded: 8 · nodes returned: 32 · approx tokens: 4028
```

The same run with `--max-hops 6 --no-prune` returns **413 nodes and about 208,000 tokens**, against about 4,000 with the guardrails on. With `--max-hops 1` it finds nothing.

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

`wander/core.py`, in short:

1. **Expand** breadth-first from all the starting points at once, following only relationships the ontology declares, up to a hop limit and a node budget.
2. **Don't wander through hubs.** If most of the population reaches a node the same way (General support, used by 64 of 67 customers), sharing it says nothing, so the walk doesn't go through it. Nor does it wander on through other customers: who else shares a thread is step 6.
3. **Converge.** Keep nodes that enough of the starting points reach (support).
4. **Discount by lift**: how much more often than chance. The Integrations queue: 5 of 5 starting points, 27 of 67 customers overall, lift 2.5.
5. **Explain, don't repeat.** Things that sit behind a finding (the reorg decision, the plan, Daniela's comment) become its explanation, not separate findings.
6. **Who else shares the thread**: other customers who reach the finding the same way.

The server runs this loop, not Claude, so the same question on the same data gives the same context every time. Only Claude's wording varies.

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
      "args": ["run", "--directory", "/path/to/teaching-software-to-wander", "python", "-m", "wander.mcp.graph"],
      "env": {"WANDER_STORE": "neo4j"}
    }
  }
}
```

Use `"WANDER_STORE": "memory"` if Neo4j isn't running. The servers (`wander/mcp/`) are thin wrappers over `wander/tools.py`: the same tools the chat app gives Claude. Only the model and system prompt are now your client's, so the comparison is a little less controlled than in the chat app.

## In Neo4j Browser

`queries/wander.cypher` is a hand-written, commented query that draws Charlene's path. Open http://localhost:7474 (user `neo4j`, password from `.env`), paste it in, and switch to the graph view.

## Tests

No Docker or API key needed:

```bash
uv run pytest
```

## What's where

```
wander/
├── core.py          the wander, the base rate, details and find   ← start here
├── guardrails.py    hop limit, node budget, support and lift
├── ontology.py      load and validate the ontology; propose, review, apply
├── proposals.py     the same, with the graph kept in step
├── tools.py         both toolsets, defined once
├── render.py        readable text for tool results
├── stores/          where the data lives: graph (Neo4j, in-memory), records (SQLite)
├── chat/            the tool-use loop and the shared system prompt
├── mcp/             the optional MCP servers
├── viewer/          the ontology viewer and its Review page
└── cli.py           the command line
```

The top level of `wander/` is the idea itself, and knows nothing about Claude. `tools.py` turns it into tools an agent can call; the subfolders are where the data lives and the ways in.

| Elsewhere | What it is |
|---|---|
| `app.py`, `chainlit.md` | The chat app (Chainlit wants them at the root) |
| `public/`, `.chainlit/config.toml` | The chat app's look: logo, avatars, colours, and the Records / Graph switch |
| `ontology.yaml` | The live ontology (`ontology.initial.yaml` is the starting point) |
| `data/generate.py`, `data/scenarios/` | The company and the five planted stories |
| `data/generated/` | The generated data, committed so everyone gets the same |
| `queries/wander.cypher` | A hand-written query that draws Charlene's path in Neo4j Browser |
| `tests/` | The tests: no Docker or API key needed |

## Possible extensions

- Sign-in for the viewer: proposals already wait for a developer's review, but the viewer only listens on localhost and anyone who can open it can also open the Review page. Opening it to a whole organisation would need sign-in, with only developers allowed to apply.
- Causal inference: the base rate is a signal, not proof. That's the next article.
