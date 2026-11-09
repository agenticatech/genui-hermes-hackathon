"""Agent half of the genui plugin: the live-component tools and the turn hint.

show_component / update_component validate props against the component's schema, store them per
chat (library.Store), then push the new state to the Desktop half as the plugin event
`plugin.genui.component`, which repaints the card in place.
"""
import json
import logging

from . import library, prompt

logger = logging.getLogger(__name__)

PLUGIN_ID = "genui"
_ctx = None
_components = None


def _settings() -> dict:
    """This agent's theme choice: plugins.entries.genui.settings.{theme, overrides} in its config."""
    if _ctx is None:
        return {}
    try:
        return {"theme": _ctx.get_config("theme"), "overrides": _ctx.get_config("overrides")}
    except Exception:
        logger.warning("genui: could not read the theme settings", exc_info=True)
        return {}


def _broadcast(record: dict) -> None:
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event(PLUGIN_ID, "component", {k: record[k] for k in ("key", "id", "type", "theme", "props", "rev")})
    except Exception:  # no Desktop attached (hermes chat, cron): the stored state is still served on load
        logger.warning("genui: component event not delivered", exc_info=True)


def components() -> library.Components:
    global _components
    if _components is None:
        from plugins.plugin_storage import plugin_data_dir
        _components = library.Components(library.Store(plugin_data_dir(PLUGIN_ID) / "components"),
                                         settings=_settings, broadcast=_broadcast)
    return _components


def show_component(args: dict, session_id=None, **kwargs) -> str:
    return json.dumps(components().show(session_id, args or {}), ensure_ascii=False)


def update_component(args: dict, session_id=None, **kwargs) -> str:
    return json.dumps(components().update(session_id, args or {}), ensure_ascii=False)


def ask_user(args: dict, **kwargs) -> str:
    # A plugin tool cannot wait for the user (Hermes' own clarify tool runs inside the agent loop),
    # so the question goes in the reply and the answer arrives as the next user message.
    if not str((args or {}).get("question") or "").strip():
        return json.dumps({"ok": False, "errors": ["question is required"]})
    return json.dumps({"ok": True, "next": "Write this question as your reply and end your turn: the "
                                           "user's answer comes back as their next message."})


HANDLERS = {"show_component": (show_component, "🃏"), "update_component": (update_component, "🔄"), "ask_user": (ask_user, "❔")}


def pre_llm_call(platform=None, **kwargs):
    # Plugin tools sit behind tool_search, so the model only sees their names: this hint, added to
    # every Desktop turn, carries the rules. Other platforms do not render ::genui directives.
    return {"context": prompt.turn_hint()} if platform == "desktop" else None


def register(ctx):
    global _ctx
    _ctx = ctx
    for schema in prompt.tool_schemas():
        handler, emoji = HANDLERS[schema["name"]]
        ctx.register_tool(name=schema["name"], toolset=PLUGIN_ID, schema=schema, handler=handler, emoji=emoji)
    ctx.register_hook("pre_llm_call", pre_llm_call)
