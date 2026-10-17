"""A plain Anthropic SDK tool-use loop, shared by both agents in the chat app.

No agent framework: send the conversation and the tools, run whatever tools Claude asks
for (via tools.py), feed the results back, and repeat until Claude answers. The final
answer streams out through `on_text`. A cap on tool calls per answer is another visible
guardrail.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import anthropic

from wander import tools
from wander.chat import prompts

# Models that accept server-side refusal fallbacks ("default" routing) on the Claude API.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict
    title: str
    is_error: bool
    seconds: float


@dataclass
class Answer:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    seconds: float = 0.0
    hit_cap: bool = False
    stop_reason: str | None = None

    def footer(self) -> str:
        total_in = self.input_tokens + self.cache_read_tokens
        parts = [f"{len(self.tool_calls)} tool call{'s' if len(self.tool_calls) != 1 else ''}",
                 f"{total_in:,} input tokens", f"{self.output_tokens:,} output tokens",
                 f"{self.seconds:.0f}s"]
        if self.hit_cap:
            parts.append(f"stopped at the {prompts.SETTINGS['max_tool_calls']}-call limit")
        return " · ".join(parts)


OnText = Callable[[str], Awaitable[None]]
OnToolStart = Callable[[str, dict], Awaitable[object]]
OnToolEnd = Callable[[object, ToolCall], Awaitable[None]]


async def answer(messages: list[dict], toolset: str, ctx: tools.Context, model: str | None = None,
                 on_text: OnText | None = None, on_tool_start: OnToolStart | None = None,
                 on_tool_end: OnToolEnd | None = None,
                 client: anthropic.AsyncAnthropic | None = None) -> Answer:
    """Run the loop. `messages` is the conversation so far and is extended in place."""
    client = client or anthropic.AsyncAnthropic()
    model = model or prompts.model()
    tool_specs = [t.api_spec() for t in tools.TOOLSETS[toolset]]
    cap = prompts.SETTINGS["max_tool_calls"]
    result = Answer()
    started = time.monotonic()
    out_of_calls = False

    while True:
        extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if model in FALLBACK_MODELS else {}
        async with client.beta.messages.stream(
            model=model,
            max_tokens=prompts.SETTINGS["max_tokens"],
            system=prompts.SYSTEM_PROMPT,
            tools=tool_specs,
            tool_choice={"type": "none"} if out_of_calls else {"type": "auto"},
            output_config={"effort": prompts.SETTINGS["effort"]},
            cache_control={"type": "ephemeral"},
            messages=messages,
            **extra,
        ) as stream:
            async for event in stream:
                if event.type == "text" and on_text:
                    await on_text(event.text)
            response = await stream.get_final_message()

        usage = response.usage
        result.input_tokens += usage.input_tokens + (usage.cache_creation_input_tokens or 0)
        result.cache_read_tokens += usage.cache_read_input_tokens or 0
        result.output_tokens += usage.output_tokens
        result.stop_reason = response.stop_reason
        # Append the whole content (thinking blocks included): the history stays append-only.
        messages.append({"role": "assistant", "content": response.content})
        result.text += "".join(b.text for b in response.content if b.type == "text")

        if response.stop_reason == "pause_turn":
            continue
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason in ("refusal", "max_tokens") or not tool_uses:
            break

        results = []
        for block in tool_uses:
            if len(result.tool_calls) >= cap:
                result.hit_cap = out_of_calls = True
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": f"Tool call limit reached ({cap} per answer). "
                                           "Answer with what you have found so far."})
                continue
            handle = await on_tool_start(block.name, block.input) if on_tool_start else None
            t0 = time.monotonic()
            output, title, is_error = await asyncio.to_thread(tools.run, toolset, block.name, block.input, ctx)
            call = ToolCall(block.name, block.input, output, title, is_error, time.monotonic() - t0)
            result.tool_calls.append(call)
            if on_tool_end:
                await on_tool_end(handle, call)
            results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": is_error,
                            "content": json.dumps(output, ensure_ascii=False, default=str)})
        messages.append({"role": "user", "content": results})

    result.seconds = time.monotonic() - started
    return result
