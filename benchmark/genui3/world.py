"""Simulated environment: domain tools return scripted results, in order, per tool.

Task format:
  "world": {
    "tools": {"git_push": {"description": "...", "input_schema": {...}, "results": [{...}, ...]}, ...},
    "requires_user_action": {
      "merge_pr": "merge",                                   # regex on the action_id the user clicked
      "delete_files": {"action": "delete|clean",             # same, and the call's paths must be within
                       "scope": {"arg": "paths", "values": "selected"}},   # what that click selected
    }
  }
A gated tool refuses to run without a matching decision: an agent must not be able to "succeed" by
skipping consent, nor by acting on more than the user chose.
"""
from __future__ import annotations

import copy
import re

REFUSED = "needs an explicit user decision"


class World:
    def __init__(self, spec: dict):
        self.spec = spec
        self.calls: dict[str, int] = {}

    def tool_schemas(self) -> list[dict]:
        return [{"name": n, "description": t.get("description", ""), "input_schema": t.get("input_schema", {"type": "object"})}
                for n, t in self.spec["tools"].items()]

    def has(self, name: str) -> bool:
        return name in self.spec["tools"]

    def _refusal(self, name: str, args: dict, user_actions: list[dict]) -> str | None:
        gate = self.spec.get("requires_user_action", {}).get(name)
        if not gate:
            return None
        if isinstance(gate, str):
            gate = {"action": gate}
        decision = next((a for a in reversed(user_actions) if re.search(gate["action"], a["action_id"], re.I)), None)
        if decision is None:
            return f"{name} {REFUSED} first"
        scope = gate.get("scope")
        if scope:
            asked = args.get(scope["arg"])
            asked = asked if isinstance(asked, list) else [asked]
            allowed = decision.get("values", {}).get(scope["values"]) or []
            allowed = allowed if isinstance(allowed, list) else [allowed]
            outside = [a for a in asked if a not in allowed]
            if outside:
                return f"{name} {REFUSED} covering {outside}: the user did not select them"
        return None

    def call(self, name: str, args: dict, user_actions: list[dict]) -> dict:
        refusal = self._refusal(name, args if isinstance(args, dict) else {}, user_actions)
        if refusal:
            return {"ok": False, "error": refusal}
        results = self.spec["tools"][name]["results"]
        i = self.calls.get(name, 0)
        self.calls[name] = i + 1
        return copy.deepcopy(results[min(i, len(results) - 1)])
