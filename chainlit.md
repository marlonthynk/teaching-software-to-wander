# Teaching software to wander

The same company data, stored two ways, and the same Claude, asked the same question.

- **Records**: an ordinary store. Records and keyword search, the way most teams' systems look.
- **Graph**: the same data as a graph. Claude calls one `wander` tool that walks out from what you care about, keeps where the paths converge, and prunes the rest.

**Try this:** the app opens in **Graph**. Ask *"Why did the five customers who churned in Q3 2026 leave?"*, then switch to **Records** at the top (that starts a new chat) and ask it again. The ⓘ next to the switch explains the difference.

**What to look for:** open the tool steps under each answer to see exactly what each agent looked at and the raw context it received. The footer shows how much work each answer took. To teach the Graph mode something new, open the ontology viewer (`uv run python -m wander.cli viewer`), propose it with **+ Add knowledge**, and apply it on the viewer's Review page; then ask again.
