"""The chat app: ask a question in Records, then switch to Graph and ask it again.

    uv run chainlit run app.py

Two modes, as Chainlit chat profiles. Switching profile starts a new chat, so the two
agents never share a conversation. Both use the same model, system prompt and settings;
the only difference is the toolset.
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
import chainlit as cl
from chainlit.input_widget import Select
from dotenv import load_dotenv

from wander import tools
from wander.chat import agent, prompts
from wander.render import render

load_dotenv()

ROOT = Path(__file__).resolve().parent
MODES = {
    "Records": ("records", "An ordinary store: records and keyword search."),
    "Graph": ("graph", "The same data as a graph the agent can wander."),
}


def _scenarios() -> list[dict]:
    path = ROOT / "data" / "generated" / "scenarios.json"
    return json.loads(path.read_text()) if path.exists() else []


def _starters() -> list[cl.Starter]:
    return [cl.Starter(label=s["question"], message=s["question"]) for s in _scenarios()]


@cl.set_chat_profiles
async def chat_profiles(current_user=None, language=None):
    return [cl.ChatProfile(name=name, markdown_description=desc, default=(name == "Graph"),
                           starters=_starters())
            for name, (_, desc) in MODES.items()]


@cl.on_chat_start
async def start():
    mode = cl.user_session.get("chat_profile") or "Graph"
    cl.user_session.set("mode", mode)
    cl.user_session.set("messages", [])
    cl.user_session.set("ctx", tools.Context())
    cl.user_session.set("model", prompts.model())
    models = list(dict.fromkeys([prompts.model(), *prompts.MODELS]))
    await cl.ChatSettings([Select(id="model", label="Model (the same for both modes)",
                                  values=models, initial_value=prompts.model())]).send()


@cl.on_settings_update
async def settings_update(settings):
    cl.user_session.set("model", settings["model"])


@cl.on_message
async def on_message(message: cl.Message):
    mode = cl.user_session.get("mode")
    toolset = MODES[mode][0]
    history: list = cl.user_session.get("messages")
    history.append({"role": "user", "content": message.content})
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
        result = await agent.answer(history, toolset, cl.user_session.get("ctx"),
                                    model=cl.user_session.get("model"), on_text=on_text,
                                    on_tool_start=on_tool_start, on_tool_end=on_tool_end)
    except anthropic.AuthenticationError:
        reply.content = "No valid `ANTHROPIC_API_KEY` found. Add one to `.env` and restart."
        await reply.update()
        return
    except anthropic.APIError as e:
        reply.content = f"The Claude API returned an error: {e}"
        await reply.update()
        return
    except Exception as e:  # e.g. no credentials at all, or Neo4j isn't running
        if "authentication" in str(e).lower():
            text = "No `ANTHROPIC_API_KEY` found. Add one to `.env` and restart the app."
        elif "neo4j" in type(e).__module__ or "7687" in str(e):
            text = ("Can't reach Neo4j. Start it with `docker compose up -d`, or set "
                    "`WANDER_STORE=memory` in `.env` and restart.")
        else:
            text = f"Something went wrong: {e}"
        reply.content = text
        await reply.update()
        return

    if result.stop_reason == "refusal" and not result.text:
        await reply.stream_token("Claude declined to answer this one.")
    await reply.stream_token(f"\n\n---\n*{mode} · {result.footer()}*")
    await reply.update()
