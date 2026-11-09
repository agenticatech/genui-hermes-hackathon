"""The plugin as Hermes loads it: a package whose register(ctx) wires the tools, with Hermes'
storage and event modules replaced by fakes."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"
PR = {"title": "Refresh sessions", "status": "committing", "commits": []}


class Ctx:
    def __init__(self, settings):
        self.tools, self.hooks, self.settings = {}, {}, settings

    def register_tool(self, name, toolset, schema, handler, emoji):
        assert schema["name"] == name and toolset == "genui"
        self.tools[name] = handler

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def get_config(self, key, default=None):
        return self.settings.get(key, default)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    events = []
    storage = types.ModuleType("plugins.plugin_storage")
    storage.plugin_data_dir = lambda pid: tmp_path / pid
    bridge = types.ModuleType("hermes_cli.plugin_events")
    bridge.broadcast_plugin_event = lambda pid, event, payload: events.append((pid, event, payload))
    for name, mod in {"plugins": types.ModuleType("plugins"), "plugins.plugin_storage": storage,
                      "hermes_cli": types.ModuleType("hermes_cli"), "hermes_cli.plugin_events": bridge}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    spec = importlib.util.spec_from_file_location("genui_under_test", PLUGIN / "__init__.py",
                                                  submodule_search_locations=[str(PLUGIN)])
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "genui_under_test", mod)
    spec.loader.exec_module(mod)
    ctx = Ctx({"theme": "default"})
    mod.register(ctx)
    yield ctx, events
    for name in [n for n in sys.modules if n.startswith("genui_under_test.")]:
        del sys.modules[name]


def test_register_exposes_the_contract(plugin):
    ctx, _ = plugin
    assert set(ctx.tools) == {"show_component", "update_component", "ask_user"}
    assert set(ctx.hooks) == {"pre_llm_call"}
    manifest = (PLUGIN / "plugin.yaml").read_text(encoding="utf-8")
    assert "render_micro_app" not in manifest and all(t in manifest for t in ctx.tools)


def test_tools_store_and_broadcast(plugin):
    ctx, events = plugin
    show = json.loads(ctx.tools["show_component"]({"id": "pr", "type": "pr_card", "props": PR}, session_id="s1", task_id="t"))
    assert show["ok"] is True and show["directive"].startswith('::genui{id="')
    upd = json.loads(ctx.tools["update_component"]({"id": "pr", "patch": {"status": "pushing"}}, session_id="s1"))
    assert upd == {"ok": True}
    bad = json.loads(ctx.tools["update_component"]({"id": "pr", "patch": {"status": "nope"}}, session_id="s1"))
    assert bad["ok"] is False and bad["errors"]
    assert [(pid, ev, p["rev"], p["props"]["status"]) for pid, ev, p in events] == [
        ("genui", "component", 1, "committing"), ("genui", "component", 2, "pushing")]
    assert events[0][2]["id"] == "pr" and events[0][2]["theme"] == "default"


def test_ask_user_and_hint(plugin):
    ctx, _ = plugin
    assert json.loads(ctx.tools["ask_user"]({"question": "Which branch?"}))["ok"] is True
    assert json.loads(ctx.tools["ask_user"]({}))["ok"] is False
    hint = ctx.hooks["pre_llm_call"](platform="desktop")["context"]
    assert "show_component" in hint and "user_action" in hint and "values.selected" in hint
    assert all(t in hint for t in ("pr_card", "task_card", "review_list"))
    assert ctx.hooks["pre_llm_call"](platform="cli") is None
