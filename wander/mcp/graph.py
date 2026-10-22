"""Optional MCP server: the same data as a graph, with the wander.

    uv run python -m wander.mcp.graph      (needs Neo4j: docker compose up -d)
"""

from wander.mcp.server import serve

if __name__ == "__main__":
    serve("graph", "company-graph")
