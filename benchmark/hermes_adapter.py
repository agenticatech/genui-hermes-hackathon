"""v3 adapter: the model Hermes runs, given exactly the prompt and tools the GenUI plugin ships.

The v3 runner owns the loop (one model response per step) and executes every tool itself, including
the scripted tools Hermes does not have, so this adapter stands in for Hermes: it builds the same
request Hermes would (system prompt, tools, conversation) and sends it to the model through the
Anthropic API. It measures what the plugin controls (the turn hint, the tool descriptions, the
component schemas, read from plugin/prompt.py), not Hermes' own runtime. A click reaches the model as
the same user turn the Desktop half sends.

    python benchmark/run_eval.py --agent hermes_adapter:HermesAgent

GENUI_ARM=plugin (default) gives the model the plugin; GENUI_ARM=baseline is Hermes without it:
the task's own tools plus a plain question tool standing in for Hermes' clarify, and no turn hint.
Model: GENUI_MODEL, else HERMES_MODEL (.env). Effort: GENUI_EFFORT, else the model's default.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from genui3.runner import AgentStep

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin"))
import prompt  # noqa: E402  (the plugin's own turn hint and tool schemas)

load_dotenv(ROOT / ".env")

# Hermes' own system prompt is long and not ours to measure; this stands in for it.
PREAMBLE = ("You are Hermes, an AI agent that works in the user's repository through tools. Carry the task "
            "through with your tools and keep your replies short.")
PLUGIN_TOOLS = {"show_component", "update_component", "ask_user"}
# The baseline's stand-in for Hermes' clarify tool (the runner answers it like ask_user).
CLARIFY = {"name": "ask_user", "description": "Ask the user a question in plain text and wait for their answer.",
           "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}


def user_action_text(component_id: str, action_id: str, values: dict | None = None) -> str:
    """The turn plugin/desktop/plugin.js submits on a click (its userActionText, JSON.stringify)."""
    event = {"type": "user_action", "component_id": component_id, "action_id": action_id}
    if values:
        event["values"] = values
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False)


class HermesAgent:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("GENUI_MODEL") or os.environ.get("HERMES_MODEL") or "claude-sonnet-5-5"
        self.effort = os.environ.get("GENUI_EFFORT")
        self.arm = os.environ.get("GENUI_ARM", "plugin")

    def reset(self, task: dict, tools: list[dict]) -> None:
        world = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("input_schema") or {"type": "object"}}
                 for t in tools if t["name"] not in PLUGIN_TOOLS]
        if self.arm == "baseline":
            self.tools = world + [CLARIFY]
            self.system = PREAMBLE
        else:
            plugin = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in prompt.tool_schemas()]
            self.tools = plugin + world
            self.system = f"{PREAMBLE}\n\n{prompt.turn_hint()}"
        self.messages: list[dict] = []
        self.pending: list[str] = []  # tool_use ids of the last response, in call order
        self.fallbacks = 0

    def _content(self, obs: list[dict]) -> list[dict]:
        content = []
        results = [o for o in obs if o["type"] == "tool_result"]
        if len(results) != len(self.pending):
            raise RuntimeError(f"{len(self.pending)} tool calls but {len(results)} results")
        for tool_use_id, o in zip(self.pending, results):
            result = o["result"]
            block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(result, ensure_ascii=False)}
            if isinstance(result, dict) and result.get("ok") is False:
                block["is_error"] = True
            content.append(block)
        for o in obs:
            if o["type"] == "user_message":
                text = o["text"]
                if o.get("context"):  # what the agent would know from a first look at the repo
                    text += "\n\n[Workspace state]\n" + json.dumps(o["context"], ensure_ascii=False, indent=1)
                content.append({"type": "text", "text": text})
            elif o["type"] == "user_action":
                content.append({"type": "text", "text": user_action_text(o["component_id"], o["action_id"], o.get("values"))})
        return content

    def step(self, obs: list[dict]) -> AgentStep:
        content = self._content(obs)
        self.pending = []
        if not content:
            return AgentStep()
        self.messages.append({"role": "user", "content": content})
        text, calls = self._respond()
        return AgentStep(text=text, tool_calls=calls)

    def _respond(self) -> tuple[str, list[dict]]:
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            cache_control={"type": "ephemeral"},  # the growing conversation is re-read every step
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **extra,
        )
        if any(getattr(it, "type", None) == "fallback_message" for it in (getattr(response.usage, "iterations", None) or [])):
            self.fallbacks += 1
            print(f"   [adapter] a refusal fallback served this step ({response.model})", file=sys.stderr)
        # Thinking blocks included, unchanged: the conversation stays append-only.
        self.messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason in ("refusal", "max_tokens"):
            print(f"   [adapter] stop_reason={response.stop_reason}", file=sys.stderr)
        calls = []
        for block in response.content:
            if block.type == "tool_use":
                self.pending.append(block.id)
                calls.append({"tool": block.name, "args": block.input})
        return "".join(block.text for block in response.content if block.type == "text"), calls

