"""The v3 adapter without the API: a fake client plays the model, the real runner and graders run.
Checks the message plumbing (tool_result ids, user_action turns, plugin tool definitions) before a
paid run."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

BENCH = Path(__file__).resolve().parent.parent / "benchmark"
sys.path.insert(0, str(BENCH))

import hermes_adapter  # noqa: E402
from genui3.grader import grade  # noqa: E402
from genui3.runner import run_task  # noqa: E402
from genui3.sim import ScriptedUser  # noqa: E402


def tool_use(i, name, **args):
    return NS(type="tool_use", id=f"tu_{i}", name=name, input=args)


class FakeModel:
    """Shows the card, commits, then asks before merging main in; reacts to the click."""

    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: o.__dict__)))
        n = len(self.calls)
        props = {"title": "Refresh sessions", "status": "committing", "commits": []}
        script = {
            1: [tool_use(1, "show_component", id="pr", type="pr_card", props=props), tool_use(2, "git_commit")],
            2: [tool_use(3, "update_component", id="pr", patch={"status": "conflicts", "explanation": "auth.ts and middleware.ts",
                                                                "actions": [{"id": "resolve_conflicts", "label": "Resolve conflicts"}]})],
            3: [NS(type="text", text="Waiting for your decision.")],
            4: [tool_use(4, "update_component", id="pr", patch={"status": "resolving", "explanation": None, "actions": []})],
            5: [NS(type="text", text="Stopping here.")],
        }[n]
        stop = "tool_use" if any(b.type == "tool_use" for b in script) else "end_turn"
        return NS(content=script, stop_reason=stop, model="fake", usage=NS(iterations=None))


def test_adapter_plumbing(monkeypatch):
    fake = FakeModel()
    agent = hermes_adapter.HermesAgent.__new__(hermes_adapter.HermesAgent)
    agent.client = NS(beta=NS(messages=fake))
    agent.model, agent.effort, agent.arm = "fake", None, "plugin"
    task = json.loads((BENCH / "tasks_v3.jsonl").read_text(encoding="utf-8").splitlines()[0])
    trace = run_task(task, agent, ScriptedUser(task), themes_dir=BENCH.parent / "plugin" / "themes")

    first = fake.calls[0]
    names = [t["name"] for t in first["tools"]]
    assert names[:3] == ["show_component", "update_component", "ask_user"] and "git_commit" in names
    assert "Library (type: props JSON Schema)" in first["tools"][0]["description"]   # the plugin's text, not the runner's
    assert "[GenUI plugin]" in first["system"]
    assert "[Workspace state]" in first["messages"][0]["content"][0]["text"]

    second = fake.calls[1]["messages"]
    results = second[-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]
    assert json.loads(results[0]["content"]) == {"ok": True}

    # Turn 3 ended the turn; the scripted user clicked; the model got the Desktop's exact turn.
    click = fake.calls[3]["messages"][-1]["content"][-1]["text"]
    assert json.loads(click) == {"type": "user_action", "component_id": "pr", "action_id": "resolve_conflicts"}
    roles = [m["role"] for m in fake.calls[-1]["messages"]]
    assert all(a != b for a, b in zip(roles, roles[1:]))                              # strictly alternating

    checks = {c["check"]: c["status"] for c in grade(task, trace)["checks"]}
    assert checks["component_choice"] == "pass" and checks["decision_offered:resolve"] == "pass"
    assert checks["zero_render_errors"] == "pass"


def test_baseline_arm_has_no_plugin():
    agent = hermes_adapter.HermesAgent.__new__(hermes_adapter.HermesAgent)
    agent.arm = "baseline"
    tools = [{"name": "show_component"}, {"name": "update_component"}, {"name": "ask_user"},
             {"name": "git_push", "description": "Push.", "input_schema": {"type": "object"}}]
    agent.reset({}, tools)
    assert [t["name"] for t in agent.tools] == ["git_push", "ask_user"]
    assert "GenUI" not in agent.system and "component" not in agent.tools[1]["description"]
    assert hermes_adapter.user_action_text("d", "delete", {"selected": ["a"]}) == \
        '{"type":"user_action","component_id":"d","action_id":"delete","values":{"selected":["a"]}}'
