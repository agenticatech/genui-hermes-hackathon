"""Episode runner for GenUI v3: living components driven by the agent's work.

One agent step = one model response (text + tool calls). Every tool call gets a result:
  show_component / update_component   -> applied to the page, result {"ok": bool, "errors": [...]}
  domain tools (from the task's world) -> scripted result
When a step has no tool call, the agent has ended its turn: the simulated user may fill the
component's fields and click an action it offers, which comes back as
{"type": "user_action", "component_id", "action_id", "values"?}. Otherwise the episode ends.

values is what the user chose in the component when they clicked: the host reads every element
marked data-field="<name>" (checked checkboxes of one field become a list of their values, a range
or number input a number, anything else its value). A theme may pass more with emit(id, values).
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from playwright.sync_api import Page, sync_playwright

from .world import World

ROOT = Path(__file__).resolve().parent.parent
THEMES = ROOT.parent / "plugin" / "themes"  # the plugin's themes: what users see is what is graded
MOTION = ROOT.parent / "plugin" / "motion.js"  # the motion kit the themes animate with (GenUI.motion)

HOST = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:16px;background:#f6f8f9">
<div id="chat" style="display:flex;flex-direction:column;gap:12px"></div>
<script>
window.__events = [];
window.GenUI = { r: {}, register(t, f) { this.r[t] = f }, get motion() { return window.GenUIMotion } };
window.__values = (el) => {
  const v = {};
  for (const f of el.querySelectorAll('[data-field]')) {
    const k = f.dataset.field;
    if (f.type === 'checkbox') { (v[k] = v[k] || []); if (f.checked) v[k].push(f.value); }
    else if (f.type === 'radio') { if (f.checked) v[k] = f.value; else if (!(k in v)) v[k] = null; }
    else if (f.type === 'range' || f.type === 'number') v[k] = f.value === '' ? null : Number(f.value);
    else v[k] = f.value;
  }
  return v;
};
window.__paint = (id, props) => {
  const el = document.querySelector(`[data-cid="${CSS.escape(id)}"]`);
  const emit = (a, extra) => __events.push({type: 'user_action', id, action_id: a, values: Object.assign(__values(el), extra || {})});
  try { GenUI.r[el.dataset.type](el, props, emit) }
  catch (e) { __events.push({type: 'error', id, message: String(e)}) }
};
window.__show = (id, type, props) => {
  let el = document.querySelector(`[data-cid="${CSS.escape(id)}"]`);
  if (!el) { el = document.createElement('section'); el.dataset.cid = id; document.getElementById('chat').append(el) }
  el.dataset.type = type; __paint(id, props);
};
</script></body></html>"""

UI_TOOLS = {"show_component", "update_component", "ask_user"}


def merge_patch(target, patch):
    """RFC 7386 JSON Merge Patch."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    out = copy.deepcopy(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge_patch(out.get(k), v)
    return out


@dataclass
class AgentStep:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # [{"tool": name, "args": {...}}]


class Agent(Protocol):
    def reset(self, task: dict, tools: list[dict]) -> None: ...
    def step(self, observations: list[dict]) -> AgentStep: ...


def ui_tool_schemas(library: dict[str, dict]) -> list[dict]:
    types = sorted(library)
    return [
        {"name": "show_component", "description": "Show a component from the library early, before long work. One component per entity.",
         "input_schema": {"type": "object", "required": ["id", "type", "props"],
                          "properties": {"id": {"type": "string"}, "type": {"enum": types}, "props": {"type": "object"}}}},
        {"name": "update_component", "description": "JSON Merge Patch on a shown component's props. Call it after every tool result.",
         "input_schema": {"type": "object", "required": ["id", "patch"],
                          "properties": {"id": {"type": "string"}, "patch": {"type": "object"}}}},
        {"name": "ask_user", "description": "Plain-text question when no UI is needed.",
         "input_schema": {"type": "object", "required": ["question"], "properties": {"question": {"type": "string"}}}},
    ]


def load_library() -> dict[str, dict]:
    return {p.name.removesuffix(".schema.json"): json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "library").glob("*.schema.json")}


class Episode:
    def __init__(self, page: Page, task: dict, sim, library: dict[str, dict]):
        self.page, self.task, self.sim, self.library = page, task, sim, library
        self.world = World(task["world"])
        self.trace: list[dict] = []
        self.props: dict[str, dict] = {}
        self.types: dict[str, str] = {}
        self.user_actions: list[dict] = []  # {"action_id", "values"}, oldest first
        self.step_no, self._seen = 0, 0
        self.t0 = time.monotonic()

    def log(self, ev: dict) -> dict:
        ev = {"step": self.step_no, "t_ms": int((time.monotonic() - self.t0) * 1000), **ev}
        self.trace.append(ev)
        return ev

    def _validate(self, ctype: str, props: dict) -> list[str]:
        import jsonschema
        schema = self.library.get(ctype)
        if schema is None:
            return [f"unknown component type {ctype!r}"]
        return [e.message[:120] for e in jsonschema.Draft202012Validator(schema).iter_errors(props)][:5]

    def _drain(self) -> list[dict]:
        evs = self.page.evaluate("window.__events")
        new, self._seen = evs[self._seen:], len(evs)
        for e in new:
            if e["type"] == "error":
                self.log({"kind": "render_error", "id": e["id"], "message": e["message"]})
        return [e for e in new if e["type"] == "user_action"]

    def ui_call(self, tool: str, args: dict) -> dict:
        if tool == "ask_user":
            self.log({"kind": "ask_user", "text": args.get("question", "")})
            return {"ok": True, "reply": self.sim.reply(args.get("question", ""))}
        cid = str(args.get("id", ""))
        if tool == "show_component":
            ctype, props = args.get("type", ""), args.get("props", {})
            errs = self._validate(ctype, props)
            self.log({"kind": "show", "id": cid, "type": ctype, "props": props, "reshow": cid in self.props, "errors": errs})
            if not errs:
                self.props[cid], self.types[cid] = props, ctype
                self.page.evaluate("([i, t, p]) => __show(i, t, p)", [cid, ctype, props])
        else:
            if cid not in self.props:
                errs = [f"no component with id {cid!r}"]
                self.log({"kind": "update", "id": cid, "patch": args.get("patch", {}), "props": None, "errors": errs})
                return {"ok": False, "errors": errs}
            new = merge_patch(self.props[cid], args.get("patch", {}))
            errs = self._validate(self.types[cid], new)
            self.log({"kind": "update", "id": cid, "patch": args.get("patch", {}), "props": new, "errors": errs})
            if not errs:
                self.props[cid] = new
                self.page.evaluate("([i, p]) => __paint(i, p)", [cid, new])
        self._drain()
        return {"ok": not errs, **({"errors": errs} if errs else {})}

    def run(self, agent: Agent) -> list[dict]:
        tools = ui_tool_schemas(self.library) + self.world.tool_schemas()
        agent.reset(self.task, tools)
        obs = [{"type": "user_message", "text": self.task["user_prompt"], "context": self.task.get("context", {})}]
        self.log({"kind": "user_message", "text": self.task["user_prompt"]})
        max_steps = self.task.get("max_steps", 40)
        while self.step_no < max_steps:
            self.step_no += 1
            out = agent.step(obs)
            obs = []
            if out.text:
                self.log({"kind": "agent_message", "text": out.text})
            for call in out.tool_calls:
                tool, args = call.get("tool"), call.get("args", {})
                if tool in UI_TOOLS:
                    res = self.ui_call(tool, args)
                elif self.world.has(tool):
                    self.log({"kind": "tool_call", "tool": tool, "args": args})
                    res = self.world.call(tool, args, self.user_actions)
                    self.log({"kind": "tool_result", "tool": tool, "result": res})
                else:
                    res = {"ok": False, "error": f"unknown tool {tool}"}
                    self.log({"kind": "tool_call", "tool": tool, "args": args, "unknown": True})
                obs.append({"type": "tool_result", "tool": tool, "result": res})
            if out.tool_calls:
                continue
            # The agent ended its turn: the user may react to what is on screen.
            clicked = self.sim.act(self)
            acts = self._drain()
            if not acts:
                break
            for a in acts:
                values = a.get("values") or {}
                self.user_actions.append({"action_id": a["action_id"], "values": values})
                self.log({"kind": "user_action", "id": a["id"], "action_id": a["action_id"], "values": values, "label": clicked})
                obs.append({"type": "user_action", "component_id": a["id"], "action_id": a["action_id"],
                            **({"values": values} if values else {})})
        self.log({"kind": "episode_end"})
        return self.trace


def run_task(task: dict, agent: Agent, sim, theme: str = "default", screenshots: Path | None = None,
             themes_dir: Path | None = None) -> list[dict]:
    library = load_library()
    themes_dir = themes_dir or THEMES
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 720, "height": 900})
        page.set_content(HOST)
        page.add_script_tag(content=MOTION.read_text(encoding="utf-8"))
        for name in dict.fromkeys(["default", theme]):  # shared theme parts (kit.js) before the components
            kit = themes_dir / name / "kit.js"
            if kit.exists():
                page.add_script_tag(content=kit.read_text(encoding="utf-8"))
        for ctype in library:
            js_path = themes_dir / theme / f"{ctype}.js"
            if not js_path.exists():
                js_path = themes_dir / "default" / f"{ctype}.js"
            page.add_script_tag(content=js_path.read_text(encoding="utf-8"))
        ep = Episode(page, task, sim, library)
        if screenshots:  # one image per UI change, for humans and LLM judges
            screenshots.mkdir(parents=True, exist_ok=True)
            for old in screenshots.glob("*.png"):  # never mix images from a previous run
                old.unlink()
            orig = ep.ui_call

            def shot(tool, args):
                res = orig(tool, args)
                if tool != "ask_user":
                    page.wait_for_timeout(1200)  # let entrance motion, decoding text and transitions settle
                    page.screenshot(path=str(screenshots / f"{len(list(screenshots.iterdir())):03d}_{tool}.png"), full_page=True)
                return res
            ep.ui_call = shot
        try:
            return ep.run(agent)
        finally:
            browser.close()
