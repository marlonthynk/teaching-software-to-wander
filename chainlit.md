# Teaching software to wander

The same company data, stored two ways, and the same Claude, asked the same question.

- **Records**: an ordinary store. Records and keyword search, the way most teams' systems look.
- **Graph**: the same data as a graph. Claude calls one `wander` tool that walks out from what you care about, keeps where the paths converge, and prunes the rest.

**Try this:** the app opens in **Compare**. Ask *"Why did the five customers who churned in Q3 2026 leave?"* and both agents answer side by side: Records on the left, Graph on the right. To watch one on its own, pick **Records** or **Graph** at the top (that starts a new chat). The ⓘ next to the switch explains the difference.

**What to look for:** open the tool steps under each answer to see exactly what each agent looked at and the raw context it received. The footer shows how much work each answer took. To teach the Graph mode something new, open the ontology viewer (`uv run python -m wander.cli viewer`), propose it with **+ Add knowledge**, and apply it on the viewer's Review page; then ask again.
