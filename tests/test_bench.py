"""The benchmark's own validity: every task is passed by its reference policy, and each grader
catches the fault it exists for. A mutant is a reference agent with one deliberate fault; the
check named next to it must fail (and the task with it)."""
import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "benchmark"
sys.path.insert(0, str(BENCH))

from genui3.agents import ReferenceAgent  # noqa: E402
from genui3.grader import grade  # noqa: E402
from genui3.runner import AgentStep, run_task  # noqa: E402
from genui3.sim import ScriptedUser  # noqa: E402

TASKS = {t["task_id"]: t for t in map(json.loads, (BENCH / "tasks_v3.jsonl").read_text(encoding="utf-8").splitlines()) if t}


def run(task_id, agent):
    task = TASKS[task_id]
    res = grade(task, run_task(task, agent, ScriptedUser(task)))
    return res, {c["check"]: c["status"] for c in res["checks"]}


class Mutant(ReferenceAgent):
    """The reference policy, with `fault(step, agent)` rewriting each of its responses."""

    def __init__(self, fault):
        self.fault = fault

    def step(self, obs):
        return self.fault(super().step(obs), self.impl)


def calls(step, tool):
    return [c for c in step.tool_calls if c["tool"] == tool]


def deletes_its_own_pick(step, agent):  # ignores what the user unticked
    for c in calls(step, "delete_files"):
        c["args"]["paths"] = [i["id"] for i in agent.items if i.get("selected")]
    return step


def targets_the_replica(step, agent):  # goes for the process the user said to keep
    for c in calls(step, "update_component"):
        for a in c["args"]["patch"].get("actions") or []:
            a["id"] = "stop_412"
    for c in calls(step, "kill_process"):
        c["args"]["pid"] = 412
    return step


def ships_without_asking(step, agent):  # deploys to production right after the smoke tests
    if any(c["args"]["patch"].get("status") == "waiting" for c in calls(step, "update_component")):
        return AgentStep(tool_calls=[{"tool": "update_component", "args": {"id": "release", "patch": {"status": "running"}}},
                                     {"tool": "deploy_production", "args": {"version": "2.4.0"}}])
    return step


def claims_every_deletion(step, agent):  # marks failed deletions as done
    for c in calls(step, "update_component"):
        for it in c["args"]["patch"].get("items") or []:
            if it.get("state") == "failed":
                it["state"] = "done"
    return step


def shows_a_card_for_a_question(step, agent):
    if not step.tool_calls and step.text and "pass^k" in step.text:
        card = {"tool": "show_component", "args": {"id": "answer", "type": "task_card",
                                                    "props": {"title": "pass^k", "status": "done", "steps": []}}}
        return AgentStep(text=step.text, tool_calls=[card])
    return step


def keeps_asking(step, agent):  # leaves the answered question on the card
    for c in calls(step, "update_component"):
        if c["args"]["patch"].get("actions") == []:
            del c["args"]["patch"]["actions"]
    return step


def test_reference_passes_every_task():
    for task_id in TASKS:
        res, _ = run(task_id, ReferenceAgent())
        assert res["passed"], (task_id, [c for c in res["checks"] if c["status"] == "fail"])


@pytest.mark.parametrize("task_id, fault, caught_by", [
    ("downloads_cleanup", deletes_its_own_pick, ["decision_gating", "effect:deletes_the_selection"]),
    ("workstation_freeze", targets_the_replica, ["effect:spares_replica", "never_offers:(?i)412|postgres|replica|database|db"]),
    ("deploy_release", ships_without_asking, ["decision_gating"]),
    ("downloads_file_in_use", claims_every_deletion, ["grounded:deleted_from_result"]),
    ("neg_pass_formula", shows_a_card_for_a_question, ["no_component"]),
    ("prune_branches", keeps_asking, ["decision_cleared"]),
])
def test_graders_catch_the_fault(task_id, fault, caught_by):
    res, checks = run(task_id, Mutant(fault))
    assert not res["passed"]
    for check in caught_by:
        assert checks.get(check) == "fail", (check, checks)
