"""Optional MCP server: the ordinary store (records and keyword search).

    uv run python -m wander.mcp.records

For readers without an API key: register this and wander.mcp.graph in Claude Desktop, Claude
Code or any MCP client, and ask the same question in separate conversations.
"""

from wander.mcp.server import serve

if __name__ == "__main__":
    serve("records", "company-records")
