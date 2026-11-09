"""The component library and the live state of every shown component.

components/<type>/schema.json is a component's props contract (the source of truth: props are
validated against it on every show and update). themes/<theme>/<type>.js draws it. A shown
component is one record (type, theme, props, rev) stored per chat, which update_component
patches with a JSON Merge Patch (RFC 7386) and the Desktop half repaints.

No Hermes import here: the tools (__init__.py), the backend routes (dashboard/plugin_api.py) and
the tests all use this module as is.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
COMPONENTS_DIR = ROOT / "components"
THEMES_DIR = ROOT / "themes"
MOTION_JS = ROOT / "motion.js"    # the motion kit themes animate with (GenUI.motion)
RUNTIME_JS = ROOT / "runtime.js"  # runs in the Desktop's frame after the motion kit, ahead of the theme
DEFAULT_THEME = "default"
# Component types and theme names become path segments: keep them to a safe alphabet.
NAME = re.compile(r"^[a-z0-9_-]{1,64}$")
# What the Desktop's ::genui directive accepts as an id, and what component_key produces.
KEY = re.compile(r"^[a-f0-9]{16}$")
MAX_ID = 64
MAX_ERRORS = 5


def load_library(root: Path = COMPONENTS_DIR) -> dict[str, dict]:
    """{type: JSON Schema} for every components/<type>/schema.json."""
    return {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(root.glob("*/schema.json")) if NAME.match(p.parent.name)}


def validate(schema: dict, props: Any) -> list[str]:
    """Schema errors as short lines the model can act on, each prefixed with where it is."""
    from jsonschema import Draft202012Validator  # ships with Hermes; imported late so a broken
    # install fails one tool call with a clear error instead of the whole plugin at load.
    errors = sorted(Draft202012Validator(schema).iter_errors(props), key=lambda e: list(map(str, e.absolute_path)))
    out = []
    for e in errors[:MAX_ERRORS]:
        where = "props" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path)
        out.append(f"{where}: {e.message}"[:240])
    return out


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7386 JSON Merge Patch: objects merge key by key, null removes a key, anything else
    (arrays included) replaces the value whole."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    out = copy.deepcopy(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge_patch(out.get(k), v)
    return out


def component_key(session_id: str | None, component_id: str) -> str:
    """The id the Desktop knows a component by. The model's ids ("pr") are only unique within a
    chat, and a ::genui directive is rendered without knowing its chat, so the key mixes both."""
    return hashlib.sha256(f"{session_id or ''}\0{component_id}".encode("utf-8")).hexdigest()[:16]


def theme_path(theme: str, ctype: str, themes_dir: Path = THEMES_DIR) -> Path | None:
    if not (NAME.match(theme or "") and NAME.match(ctype or "")):
        return None
    path = themes_dir / theme / f"{ctype}.js"
    return path if path.is_file() else None


def resolve_theme(ctype: str, settings: dict | None, themes_dir: Path = THEMES_DIR) -> str:
    """The theme that draws `ctype` for this agent: settings.overrides[ctype], else settings.theme,
    else default. A theme that has no file for this component falls back to default."""
    settings = settings or {}
    overrides = settings.get("overrides") if isinstance(settings.get("overrides"), dict) else {}
    for theme in (overrides.get(ctype), settings.get("theme")):
        if isinstance(theme, str) and theme_path(theme, ctype, themes_dir):
            return theme
    return DEFAULT_THEME


def frame_payload(record: dict, themes_dir: Path = THEMES_DIR) -> dict | None:
    """What the Desktop half needs to build a component's frame: the record and the frame's document
    (the motion kit, the frame runtime, the theme's kit and the component's theme). Read on every
    call, so a redeployed theme shows without a restart."""
    theme = theme_path(record["theme"], record["type"], themes_dir) or theme_path(DEFAULT_THEME, record["type"], themes_dir)
    if theme is None:
        return None
    runtime = MOTION_JS.read_text(encoding="utf-8") + "\n" + RUNTIME_JS.read_text(encoding="utf-8")
    # A theme may share parts across its components in kit.js, loaded ahead of the component's file.
    kit = theme.parent / "kit.js"
    theme_js = (kit.read_text(encoding="utf-8") + "\n" if kit.is_file() else "") + theme.read_text(encoding="utf-8")
    return {**record, "document": frame_document(record["type"], runtime, theme_js)}


FRAME_HEAD = '<meta charset="utf-8">'  # the Desktop half adds the host's theme prelude right after it


def frame_document(ctype: str, runtime: str, theme_js: str) -> str:
    """The sandboxed frame's whole document: the runtime, then the theme, inline (the frame has an
    opaque origin and no network), around the one root the theme draws into. Built here, not in the
    Desktop half, so the code that runs in the Desktop renderer never writes markup that loads code."""
    def inline(js: str) -> str:
        return re.sub(r"</(script)", r"<\\/\1", js, flags=re.IGNORECASE)
    safe_type = re.sub(r"[^a-z0-9_-]", "", ctype or "")
    return (f"<!doctype html><html><head>{FRAME_HEAD}<script>{inline(runtime)}</script><script>{inline(theme_js)}</script>"
            f'</head><body><main id="genui-root" data-type="{safe_type}"></main></body></html>')


class Store:
    """One JSON file per shown component, so the backend routes (another module, maybe another
    process) read what the tools wrote."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if not KEY.match(key or ""):
            raise ValueError(f"invalid component key {key!r}")
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        try:
            return json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, record: dict) -> None:
        path = self._path(record["key"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic: a reader never sees half a record


def _error(*errors: str) -> dict:
    return {"ok": False, "errors": list(errors)}


class Components:
    """show_component / update_component, independent of Hermes: the caller passes the store, how
    to read the agent's theme settings, and how to tell the Desktop a component changed."""

    def __init__(self, store: Store, library: dict[str, dict] | None = None,
                 settings: Callable[[], dict] = dict, broadcast: Callable[[dict], None] = lambda record: None,
                 themes_dir: Path = THEMES_DIR):
        self.store, self.settings, self.broadcast, self.themes_dir = store, settings, broadcast, themes_dir
        self.library = load_library() if library is None else library
        self._lock = threading.Lock()  # parallel tool calls must not lose each other's patches

    def _commit(self, record: dict) -> None:
        self.store.put(record)
        self.broadcast(record)

    def show(self, session_id: str | None, args: dict) -> dict:
        cid, ctype, props = args.get("id"), args.get("type"), args.get("props")
        if not isinstance(cid, str) or not cid.strip() or len(cid) > MAX_ID:
            return _error(f"id must be a non-empty string of at most {MAX_ID} characters")
        if ctype not in self.library:
            return _error(f"unknown component type {ctype!r}; the library has: {', '.join(sorted(self.library))}")
        if not isinstance(props, dict):
            return _error("props must be an object")
        errors = validate(self.library[ctype], props)
        if errors:
            return _error(*errors)
        key = component_key(session_id, cid)
        with self._lock:
            if self.store.get(key) is not None:
                return _error(f"component {cid!r} is already shown: update it with update_component(id={cid!r}, patch=...) "
                              "instead of showing it again (one card per entity)")
            self._commit({"key": key, "id": cid, "type": ctype, "theme": resolve_theme(ctype, self.settings(), self.themes_dir),
                          "props": props, "rev": 1})
        return {"ok": True, "directive": f'::genui{{id="{key}"}}'}

    def update(self, session_id: str | None, args: dict) -> dict:
        cid, patch = args.get("id"), args.get("patch")
        if not isinstance(cid, str) or not cid:
            return _error("id must be the id of a shown component")
        if not isinstance(patch, dict):
            return _error("patch must be an object (JSON Merge Patch: null removes a key, arrays are replaced whole)")
        key = component_key(session_id, cid)
        with self._lock:
            record = self.store.get(key)
            if record is None:
                return _error(f"no component with id {cid!r}: show it first with show_component")
            props = merge_patch(record["props"], patch)
            errors = validate(self.library.get(record["type"], {}), props)
            if errors:
                return _error(*errors)
            self._commit({**record, "props": props, "rev": record["rev"] + 1})
        return {"ok": True}
