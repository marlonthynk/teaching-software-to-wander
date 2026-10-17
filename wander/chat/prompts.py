"""The one system prompt and the one set of model settings both chat modes share.

Fairness: Records and Graph get exactly this prompt and these settings. The only
difference between the two agents is the tool list. Nothing here mentions what the data
contains.
"""

import os

TODAY = "2026-10-01"  # "today" in the company's data

SYSTEM_PROMPT = f"""\
You are an analyst for a B2B software company. People across the business ask you \
questions about customers, support, the product and how the company runs. Today is {TODAY}.

Use your tools to look things up rather than guessing. When you answer:
- Lead with the answer, in plain language for a business reader.
- Cite what you found: names, record ids, and any paths or connections a tool returned.
- Say how confident you are and why. Treat statistical comparisons as signals, not proof.
- If you didn't find a clear answer, say so plainly rather than inventing one.
- If answering would need information your tools can't see, say what's missing.
"""

DEFAULT_MODEL = "claude-sonnet-5-5"
MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]


def model() -> str:
    return os.environ.get("WANDER_MODEL") or DEFAULT_MODEL


# Same for both modes. Effort "medium" suits multi-step tool use.
SETTINGS = {
    "max_tokens": 32000,
    "effort": "medium",
    "max_tool_calls": 15,
}
