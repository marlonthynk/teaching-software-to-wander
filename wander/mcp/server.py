"""Expose one toolset from tools.py over MCP (stdio). No logic of its own.

The tools keep their JSON Schemas from tools.py, so this uses the MCP SDK's low-level
server rather than re-declaring each tool as a typed function.
"""

from __future__ import annotations

import asyncio
import json

import mcp.types as types
from dotenv import load_dotenv
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from wander import tools


def build(toolset: str, name: str) -> Server:
    server = Server(name)
    ctx = tools.Context()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema)
                for t in tools.TOOLSETS[toolset]]

    @server.call_tool()
    async def call_tool(tool: str, arguments: dict) -> list[types.TextContent]:
        result, _, is_error = await asyncio.to_thread(tools.run, toolset, tool, arguments or {}, ctx)
        text = json.dumps(result, ensure_ascii=False, default=str)
        if is_error:
            raise ValueError(result.get("error", text))
        return [types.TextContent(type="text", text=text)]

    return server


def serve(toolset: str, name: str) -> None:
    load_dotenv()
    server = build(toolset, name)

    async def main():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(main())
