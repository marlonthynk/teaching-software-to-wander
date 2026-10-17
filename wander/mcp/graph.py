"""Optional MCP server: the same data as a graph, with the wander.

    uv run python -m wander.mcp.graph      (set WANDER_STORE=memory to run without Docker)
"""

from wander.mcp.server import serve

if __name__ == "__main__":
    serve("graph", "company-graph")
