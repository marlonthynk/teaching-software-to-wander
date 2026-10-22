"""The agent loop: fairness between the two modes, and the tool-call cap. No API key needed."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from wander import tools
from wander.chat import agent, prompts
from wander.records.store import RecordsStore


class FakeStream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        async def gen():
            for b in self.message.content:
                if b.type == "text":
                    yield NS(type="text", text=b.text)
        return gen()

    async def get_final_message(self):
        return self.message


class FakeClient:
    """Asks for `tool_calls` find calls (one per turn), then answers."""

    def __init__(self, tool_calls: int):
        self.remaining = tool_calls
        self.requests = []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **kwargs):
        self.requests.append(kwargs)
        usage = NS(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        if self.remaining > 0 and kwargs["tool_choice"]["type"] == "auto":
            self.remaining -= 1
            name = "find" if any(t["name"] == "find" for t in kwargs["tools"]) else "search"
            args = {"type": "Customer"} if name == "find" else {"query": "churn"}
            content = [NS(type="tool_use", id=f"t{len(self.requests)}", name=name, input=args)]
            return FakeStream(NS(content=content, stop_reason="tool_use", usage=usage))
        return FakeStream(NS(content=[NS(type="text", text="Done.")], stop_reason="end_turn", usage=usage))


def run(toolset, client):
    ctx = tools.Context()
    return asyncio.run(agent.answer([{"role": "user", "content": "Why?"}], toolset, ctx, client=client))


@pytest.fixture(autouse=True)
def records_db():
    try:
        RecordsStore()
    except Exception:
        from data import load_records
        load_records.load()


def test_both_modes_get_the_same_model_prompt_and_settings(ontology_file, graph):
    seen = {}
    for toolset in ("records", "graph"):
        client = FakeClient(tool_calls=1)
        run(toolset, client)
        first = dict(client.requests[0])
        names = [t["name"] for t in first.pop("tools")]
        assert set(names) == {t.name for t in tools.TOOLSETS[toolset]}
        first.pop("messages")
        seen[toolset] = first
    assert seen["records"] == seen["graph"]
    assert seen["graph"]["system"] == prompts.SYSTEM_PROMPT
    assert seen["graph"]["model"] == prompts.model()


def test_system_prompt_is_neutral():
    text = prompts.SYSTEM_PROMPT.lower()
    for word in ("queue", "reorg", "integration", "ticket", "partner", "graph", "wander"):
        assert word not in text


def test_stops_at_the_tool_call_cap(ontology_file, graph):
    cap = prompts.SETTINGS["max_tool_calls"]
    client = FakeClient(tool_calls=cap + 5)
    result = run("graph", client)
    assert len(result.tool_calls) == cap
    assert result.hit_cap and "limit" in result.footer()
    assert client.requests[-1]["tool_choice"] == {"type": "none"}
    assert result.text.endswith("Done.")


def test_footer_reports_the_work(ontology_file):
    result = run("records", FakeClient(tool_calls=2))
    assert result.footer().startswith("2 tool calls")
    assert "input tokens" in result.footer() and "output tokens" in result.footer()


def test_records_store_is_a_fair_fight():
    from collections import Counter

    from data.source import read_generated

    records = RecordsStore()
    nodes, _ = read_generated()
    in_data = Counter(n["type"] for n in nodes)
    counts = records.counts()
    assert counts["customers"] == in_data["Customer"]
    assert counts["tickets"] == in_data["Ticket"]
    assert counts["documents"] == in_data["Document"]

    five = records.list_records("customers", {"status": "churned", "churned_at": {"gte": "2026-07-01"}})
    assert five["total"] == 5 and len({c["churn_reason"] for c in five["records"]}) == 5
    # nothing hidden: the comment on the reorg plan is searchable
    assert any(h["id"] == "doc_reorg_plan" for h in records.search("routing rule"))
    # base fields only: no renewal dates or partners in the records store
    assert "renewal_date" not in records.get_record("cust_001")
    assert not records.search("Northwind", type="customers")
