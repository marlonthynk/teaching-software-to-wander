"""The chat app: ask a question of the Records store and the Graph, side by side.

    uv run chainlit run app.py

Three modes, as Chainlit chat profiles. Compare (the default) sends every question to both
agents at once and shows the two answers next to each other; Records and Graph run one of
them alone. Either way the two agents never share a conversation: each keeps its own
history. Both use the same model, system prompt and settings; the only difference is the
toolset.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import anthropic
import chainlit as cl
from chainlit.input_widget import Select
from dotenv import load_dotenv

from wander import tools
from wander.chat import agent, compare, prompts
from wander.render import render

load_dotenv()

ROOT = Path(__file__).resolve().parent
MODES = {
    "Compare": (None, "Every question goes to both agents at once, answered side by side."),
    "Records": ("records", "An ordinary store: records and keyword search."),
    "Graph": ("graph", "The same data as a graph the agent can wander."),
}
# The starter buttons: only the scenarios where the graph gives Claude context the records
# can't. The other scenarios check that the wander finds nothing when there's nothing to find
# (or nothing until the graph is taught), so both agents answer them alike. They stay as tests.
STARTERS = ["dead-queue", "feature-that-sells"]
SIDES = [("records", "Records", "records + search"), ("graph", "Graph", "wander the graph")]
STEP_TEXT_LIMIT = 4000  # each tool result shown in Compare is cut to this many characters
UPDATE_EVERY = 0.3  # seconds between redraws of the Compare element while answers stream in


def _scenarios() -> list[dict]:
    path = ROOT / "data" / "generated" / "scenarios.json"
    return json.loads(path.read_text()) if path.exists() else []


def _starters() -> list[cl.Starter]:
    by_name = {s["name"]: s for s in _scenarios()}
    return [cl.Starter(label=by_name[n]["question"], message=by_name[n]["question"])
            for n in STARTERS if n in by_name]


@cl.set_chat_profiles
async def chat_profiles(current_user=None, language=None):
    return [cl.ChatProfile(name=name, markdown_description=desc, default=(name == "Compare"),
                           starters=_starters())
            for name, (_, desc) in MODES.items()]


@cl.on_chat_start
async def start():
    mode = cl.user_session.get("chat_profile") or "Compare"
    cl.user_session.set("mode", mode)
    cl.user_session.set("histories", {"records": [], "graph": []})
    cl.user_session.set("ctx", tools.Context())
    cl.user_session.set("model", prompts.model())
    models = list(dict.fromkeys([prompts.model(), *prompts.MODELS]))
    await cl.ChatSettings([Select(id="model", label="Model (the same for both agents)",
                                  values=models, initial_value=prompts.model())]).send()


@cl.on_settings_update
async def settings_update(settings):
    cl.user_session.set("model", settings["model"])


@cl.on_message
async def on_message(message: cl.Message):
    mode = cl.user_session.get("mode")
    if mode == "Compare":
        await compare_both(message.content)
    else:
        await answer_one(mode, message.content)


async def ask(toolset: str, question: str, **callbacks) -> agent.Answer:
    """One agent, one question, on that agent's own history. On failure the question is
    taken back out of the history, so the next one starts clean."""
    history: list = cl.user_session.get("histories")[toolset]
    before = len(history)
    history.append({"role": "user", "content": question})
    try:
        return await agent.answer(history, toolset, cl.user_session.get("ctx"),
                                  model=cl.user_session.get("model"), **callbacks)
    except BaseException:
        del history[before:]
        raise


def friendly_error(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "No valid `ANTHROPIC_API_KEY` found. Add one to `.env` and restart."
    if isinstance(e, anthropic.APIError):
        return f"The Claude API returned an error: {e}"
    if "authentication" in str(e).lower():  # e.g. no credentials at all
        return "No `ANTHROPIC_API_KEY` found. Add one to `.env` and restart the app."
    if "neo4j" in type(e).__module__ or "7687" in str(e):
        return "Can't reach Neo4j. Start it with `docker compose up -d`, then try again."
    return f"Something went wrong: {e}"


async def answer_one(mode: str, question: str):
    """Records or Graph on its own: a normal chat message with the tool steps above it."""
    toolset = MODES[mode][0]
    # The tool steps are children of the answer, so Chainlit shows them above its text: a reader
    # sees what was looked at before the conclusion.
    reply = cl.Message(content="", author=mode)
    await reply.send()

    async def on_text(token: str):
        await reply.stream_token(token)

    async def on_tool_start(name: str, args: dict):
        step = cl.Step(name=f"{name}…", type="tool", show_input="json", parent_id=reply.id)
        step.input = args
        await step.send()
        return step

    async def on_tool_end(step: cl.Step, call: agent.ToolCall):
        step.name = call.title
        step.output = render(call.name, call.result)
        step.language = "text"
        if call.is_error:
            step.is_error = True
        await step.update()
        raw = cl.Step(name="raw context Claude received (JSON)", type="tool", parent_id=step.id)
        raw.output = json.dumps(call.result, indent=2, ensure_ascii=False, default=str)
        raw.language = "json"
        await raw.send()

    try:
        result = await ask(toolset, question, on_text=on_text,
                           on_tool_start=on_tool_start, on_tool_end=on_tool_end)
    except Exception as e:
        reply.content = friendly_error(e)
        await reply.update()
        return

    if result.stop_reason == "refusal" and not result.text:
        await reply.stream_token("Claude declined to answer this one.")
    await reply.stream_token(f"\n\n---\n*{mode} · {result.footer()}*")
    await reply.update()


class Redraw:
    """Sends the Compare element again at most every UPDATE_EVERY seconds while it changes."""

    def __init__(self, element: cl.CustomElement):
        self.element = element
        self.pending: asyncio.Task | None = None

    def soon(self):
        if self.pending is None:
            self.pending = asyncio.create_task(self._later())

    async def _later(self):
        await asyncio.sleep(UPDATE_EVERY)
        self.pending = None
        await self.element.update()

    async def now(self):
        if self.pending:
            self.pending.cancel()
            self.pending = None
        await self.element.update()


async def compare_both(question: str):
    """Both agents at once, each on its own history, drawn side by side as they work."""
    sides = [{"key": key, "label": label, "hint": hint, "status": "thinking", "text": "",
              "steps": [], "started": time.time() * 1000, "metrics": None, "error": None}
             for key, label, hint in SIDES]
    element = cl.CustomElement(name="Compare", props={"sides": sides, "only": None}, display="inline")
    await cl.Message(content="", author="Compare", elements=[element]).send()
    redraw = Redraw(element)

    async def run(side: dict) -> str:
        async def on_text(token: str):
            side["status"] = "writing"
            side["text"] += token
            redraw.soon()

        async def on_tool_start(name: str, args: dict):
            side["status"] = "looking"
            side["steps"].append({"title": f"{name}…", "detail": "", "running": True, "error": False})
            redraw.soon()
            return len(side["steps"]) - 1

        async def on_tool_end(index: int, call: agent.ToolCall):
            detail = render(call.name, call.result)
            if len(detail) > STEP_TEXT_LIMIT:
                detail = detail[:STEP_TEXT_LIMIT] + "\n… (cut short here; Records or Graph mode shows it all)"
            side["steps"][index] = {"title": call.title, "detail": detail, "running": False,
                                    "error": call.is_error}
            redraw.soon()

        try:
            result = await ask(side["key"], question, on_text=on_text,
                               on_tool_start=on_tool_start, on_tool_end=on_tool_end)
        except Exception as e:
            side["status"], side["error"] = "error", friendly_error(e)
            await redraw.now()
            return ""
        if result.stop_reason == "refusal" and not result.text:
            side["text"] = "Claude declined to answer this one."
        side["status"] = "done"
        side["metrics"] = {"calls": len(result.tool_calls), "seconds": result.seconds,
                           "input_tokens": result.input_tokens + result.cache_read_tokens,
                           "output_tokens": result.output_tokens, "hit_cap": result.hit_cap}
        await redraw.now()
        return result.text

    texts = await asyncio.gather(*(run(side) for side in sides))
    if all(texts):
        element.props["only"] = compare.only_in({s["key"]: t for s, t in zip(sides, texts)})
        await redraw.now()
