import json
import os
import time
from pathlib import Path

import pytest

import library
from library import Components, Store, component_key, merge_patch, resolve_theme, validate

REPO = Path(__file__).resolve().parent.parent
PR = {
    "title": "Refresh sessions in the auth middleware", "pr": None, "status": "committing",
    "status_text": "Committing 4 changed files",
    "commits": [{"sha": "c78a92", "message": "Refresh sessions near expiry", "author": "You", "state": "ok"}],
}


# --- JSON Merge Patch (RFC 7386, appendix A) -----------------------------------

@pytest.mark.parametrize("target, patch, result", [
    ({"a": "b"}, {"a": "c"}, {"a": "c"}),
    ({"a": "b"}, {"b": "c"}, {"a": "b", "b": "c"}),
    ({"a": "b"}, {"a": None}, {}),
    ({"a": "b", "b": "c"}, {"a": None}, {"b": "c"}),
    ({"a": ["b"]}, {"a": "c"}, {"a": "c"}),
    ({"a": "c"}, {"a": ["b"]}, {"a": ["b"]}),
    ({"a": {"b": "c"}}, {"a": {"b": "d", "c": None}}, {"a": {"b": "d"}}),
    ({"a": [{"b": "c"}]}, {"a": [1]}, {"a": [1]}),
    (["a", "b"], ["c", "d"], ["c", "d"]),
    ({"a": "b"}, ["c"], ["c"]),
    ({"a": "foo"}, None, None),
    ({"a": "foo"}, "bar", "bar"),
    ({"e": None}, {"a": 1}, {"e": None, "a": 1}),
    ([1, 2], {"a": "b", "c": None}, {"a": "b"}),
    ({}, {"a": {"bb": {"ccc": None}}}, {"a": {"bb": {}}}),
])
def test_merge_patch_rfc7386(target, patch, result):
    assert merge_patch(target, patch) == result


def test_merge_patch_replaces_arrays_whole_and_leaves_inputs_alone():
    target = {"checks": [{"name": "Tests", "state": "running"}, {"name": "Lint", "state": "running"}]}
    patch = {"checks": [{"name": "Tests", "state": "passed"}]}
    assert merge_patch(target, patch) == {"checks": [{"name": "Tests", "state": "passed"}]}
    assert target["checks"][0]["state"] == "running" and len(target["checks"]) == 2
    out = merge_patch(target, {})
    out["checks"].append("x")
    assert len(target["checks"]) == 2  # deep copy: the result shares nothing with the target


# --- schemas ---------------------------------------------------------------------

def test_plugin_schemas_are_the_benchmark_schemas():
    bench = {p.name.removesuffix(".schema.json"): json.loads(p.read_text(encoding="utf-8"))
             for p in (REPO / "benchmark/library").glob("*.schema.json")}
    assert library.load_library() == bench


def test_every_component_has_a_default_theme():
    lib = library.load_library()
    assert {"pr_card", "task_card", "review_list"} <= set(lib)
    for ctype in lib:
        assert library.theme_path("default", ctype) is not None, ctype


@pytest.mark.parametrize("props, where", [
    ({k: v for k, v in PR.items() if k != "title"}, "props: 'title' is a required property"),
    ({**PR, "status": "done"}, "props.status: 'done' is not one of"),
    ({**PR, "branch": "main"}, "props: Additional properties are not allowed"),
    ({**PR, "commits": [{"sha": "x", "message": "m"}]}, "props.commits[0]: 'author' is a required property"),
    ({**PR, "conflicts": {"total": -1}}, "props.conflicts.total: -1 is less than the minimum of 0"),
    ({**PR, "actions": [{"id": "merge", "label": "Merge", "kind": "yolo"}]}, "props.actions[0].kind: 'yolo' is not one of"),
])
def test_invalid_props_are_rejected_with_where(props, where):
    errors = validate(library.load_library()["pr_card"], props)
    assert errors and any(e.startswith(where) for e in errors), errors


def test_valid_props_pass():
    assert validate(library.load_library()["pr_card"], PR) == []


# --- show / update -----------------------------------------------------------------

class Bus:
    def __init__(self):
        self.events = []

    def __call__(self, record):
        self.events.append(record)


@pytest.fixture
def comps(tmp_path):
    bus = Bus()
    c = Components(Store(tmp_path), broadcast=bus)
    c.bus = bus
    return c


def test_show_then_update_repaints_with_merged_props(comps):
    res = comps.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    key = component_key("s1", "pr")
    assert res == {"ok": True, "directive": f'::genui{{id="{key}"}}'}
    assert comps.update("s1", {"id": "pr", "patch": {"pr": 128, "status": "opening_pr"}}) == {"ok": True}
    assert comps.update("s1", {"id": "pr", "patch": {"explanation": "Lena changed auth.ts",
                                                      "actions": [{"id": "resolve_conflicts", "label": "Resolve"}]}}) == {"ok": True}
    assert comps.update("s1", {"id": "pr", "patch": {"explanation": None, "actions": []}}) == {"ok": True}
    record = comps.store.get(key)
    assert record["rev"] == 4 and record["type"] == "pr_card" and record["id"] == "pr" and record["theme"] == "default"
    assert record["props"]["pr"] == 128 and "explanation" not in record["props"] and record["props"]["actions"] == []
    assert [e["rev"] for e in comps.bus.events] == [1, 2, 3, 4]
    assert comps.bus.events[-1]["props"] == record["props"]


def test_invalid_update_is_rejected_and_changes_nothing(comps):
    comps.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    res = comps.update("s1", {"id": "pr", "patch": {"status": "shipped"}})
    assert res["ok"] is False and res["errors"][0].startswith("props.status:")
    res = comps.update("s1", {"id": "pr", "patch": {"title": None}})  # removing a required key
    assert res["ok"] is False and "'title' is a required property" in res["errors"][0]
    assert comps.store.get(component_key("s1", "pr"))["props"] == PR
    assert len(comps.bus.events) == 1


def test_invalid_show_is_rejected(comps):
    assert comps.show("s1", {"id": "pr", "type": "pr_card", "props": {"title": "x"}})["ok"] is False
    assert "unknown component type" in comps.show("s1", {"id": "pr", "type": "chart", "props": {}})["errors"][0]
    assert comps.show("s1", {"id": "", "type": "pr_card", "props": PR})["ok"] is False
    assert comps.show("s1", {"id": "pr", "type": "pr_card", "props": "[]"})["ok"] is False
    assert comps.bus.events == []


def test_one_card_per_entity(comps):
    comps.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    res = comps.show("s1", {"id": "pr", "type": "pr_card", "props": {**PR, "status": "merged"}})
    assert res["ok"] is False and "update_component" in res["errors"][0]
    assert comps.store.get(component_key("s1", "pr"))["props"]["status"] == "committing"


def test_update_needs_a_shown_component(comps):
    res = comps.update("s1", {"id": "pr", "patch": {"status": "ready"}})
    assert res["ok"] is False and "show_component" in res["errors"][0]
    assert comps.update("s1", {"id": "pr", "patch": "status=ready"})["ok"] is False


def test_chats_do_not_share_components(comps):
    comps.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    assert comps.update("s2", {"id": "pr", "patch": {"status": "ready"}})["ok"] is False
    assert comps.show("s2", {"id": "pr", "type": "pr_card", "props": PR})["ok"] is True
    assert component_key("s1", "pr") != component_key("s2", "pr")


def test_state_survives_a_new_process(tmp_path):
    Components(Store(tmp_path)).show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    assert Components(Store(tmp_path)).update("s1", {"id": "pr", "patch": {"status": "pushing"}}) == {"ok": True}


def test_store_refuses_paths(tmp_path):
    assert Store(tmp_path).get("../../etc/passwd") is None
    with pytest.raises(ValueError):
        Store(tmp_path).put({"key": "../../etc/passwd"})


def test_old_cards_are_pruned_when_a_new_card_is_shown(tmp_path):
    c = Components(Store(tmp_path))
    c.show("s1", {"id": "old", "type": "pr_card", "props": PR})
    c.show("s1", {"id": "recent", "type": "pr_card", "props": PR})
    month_ago = time.time() - 31 * 86400
    old = tmp_path / f"{component_key('s1', 'old')}.json"
    crashed = tmp_path / f"{component_key('s1', 'x')}.123.456.tmp"   # a write a crash cut short
    foreign = tmp_path / "notes.json"                                 # not the store's: left alone
    crashed.write_text("{", encoding="utf-8")
    foreign.write_text("{}", encoding="utf-8")
    for f in (old, crashed, foreign):
        os.utime(f, (month_ago, month_ago))
    c.update("s1", {"id": "recent", "patch": {"status": "pushing"}})    # updates do not prune
    assert old.exists()
    c.show("s1", {"id": "new", "type": "pr_card", "props": PR})
    assert c.store.get(component_key("s1", "old")) is None
    assert c.store.get(component_key("s1", "recent")) is not None
    assert not crashed.exists() and foreign.exists()


# --- themes ------------------------------------------------------------------------

def test_theme_resolution(tmp_path):
    (tmp_path / "default").mkdir()
    (tmp_path / "default" / "pr_card.js").write_text("", encoding="utf-8")
    (tmp_path / "acme").mkdir()
    (tmp_path / "acme" / "pr_card.js").write_text("", encoding="utf-8")
    assert resolve_theme("pr_card", {}, tmp_path) == "default"
    assert resolve_theme("pr_card", {"theme": "acme"}, tmp_path) == "acme"
    assert resolve_theme("pr_card", {"theme": "default", "overrides": {"pr_card": "acme"}}, tmp_path) == "acme"
    assert resolve_theme("pr_card", {"theme": "nope"}, tmp_path) == "default"          # no such theme
    assert resolve_theme("pr_card", {"theme": "../acme"}, tmp_path) == "default"       # not a name
    assert resolve_theme("pr_card", {"overrides": {"chart": "acme"}}, tmp_path) == "default"


def test_show_records_the_agents_theme(tmp_path):
    themes = tmp_path / "themes"
    (themes / "acme").mkdir(parents=True)
    (themes / "acme" / "pr_card.js").write_text("", encoding="utf-8")
    c = Components(Store(tmp_path / "store"), settings=lambda: {"overrides": {"pr_card": "acme"}}, themes_dir=themes)
    c.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    assert c.store.get(component_key("s1", "pr"))["theme"] == "acme"
