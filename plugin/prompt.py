"""What the model reads about GenUI: the turn hint and the three tool schemas.

No Hermes import: the plugin registers these, and the v3 benchmark adapter sends the very same
text to the model, so the benchmark measures the prompt the plugin ships.
"""
from __future__ import annotations

import json

try:  # inside Hermes the plugin is a package; the benchmark and the tests put plugin/ on sys.path
    from .library import load_library
except ImportError:
    from library import load_library

TURN_HINT = """\
[GenUI plugin] This chat shows live components: pre-designed cards that follow a task while you work. \
Tools: show_component(id, type, props), update_component(id, patch), ask_user(question); load them with \
tool_describe first if they are not loaded. Library: {catalog}.
When a task matches a component, follow these rules:
1. Show it at the start of the task, before the long steps, with only what you know now (the title, \
the plan as pending steps, a "running" or "scanning" status). If the result carries a `directive` \
line, put it alone, as its own paragraph, in your next reply text: that is where the card appears.
2. After EVERY result of a work tool, update the component (status, status_text, the new data) and \
only then call the next work tool: one work tool per response, sent together with that update.
3. Never show an unverified state. A count, a size, a PR number, "passed", "done", "deleted" or \
"merged" must come from a tool result you already received. Show what you are about to do as a busy \
status ("Running checks"), never its outcome.
4. One card per entity: one PR, one release, one cleanup is one card with one id. Update it; never \
show it again.
5. Before an irreversible or risky step (merging, resolving conflicts, deploying to production, \
rolling back, deleting, stopping a process, force-pushing), do not call the tool. Add the decision to \
props.actions ([{{"id", "label", "kind"}}]), say why in props.explanation (what changes, who or what \
is affected, what happens next), end your turn and wait. The click comes back as a message \
{{"type": "user_action", "component_id": ..., "action_id": ..., "values": ...}}, where values holds \
what the user chose in the card (review_list: values.selected, the ids they ticked). Only then call \
the tool, on exactly what they chose: never more, never your own pick. In the update that starts \
that work, clear the answered question: "explanation": null, "actions": [].
6. Keep decisions to a minimum: never ask about safe, reversible or read-only steps (listing, \
scanning, measuring, building, testing, deploying to staging, committing, pushing, opening a PR). \
Do them and show them.
7. On failure, put the real cause from the tool result in explanation (the error, the failing test \
names, what was not done) and set status "failed" when the task failed; never offer the blocked \
action (no Merge while checks fail): offer the fix instead (a retry, a rollback).
Use ask_user only for a plain-text question when no component helps. Tasks that match no component \
(questions, a small file edit) stay plain text: no card."""

SUMMARIES = {
    "pr_card": "a living card for one pull request: committing, pushing, opening the PR, fetching main, "
               "merge conflicts, resolving, checks, merge",
    "task_card": "a living card for one long operation that is not a pull request: a release or deploy, a "
                 "migration, diagnosing or fixing a machine; its steps, figures, findings and log",
    "review_list": "a list the user reviews and ticks before an irreversible action on some of its items: "
                   "deleting files, pruning branches; their selection comes back as values.selected",
    "study_card": "a living card for a study session the user asks for (test me, quiz me, help me revise or "
                  "prepare an exam), not for a plain question: the plan, a quiz they answer in the card (their "
                  "answers come back in one click as values.answers), their mastery per topic, a short lesson "
                  "with flashcards, and their review schedule",
}


def turn_hint(library: dict[str, dict] | None = None) -> str:
    library = load_library() if library is None else library
    catalog = "; ".join(f"{t} ({SUMMARIES.get(t) or s.get('description', '')})" for t, s in sorted(library.items()))
    return TURN_HINT.format(catalog=catalog or "empty")


def tool_schemas(library: dict[str, dict] | None = None) -> list[dict]:
    """The three tools in Hermes' format ({name, description, parameters})."""
    library = load_library() if library is None else library
    types = sorted(library)
    catalog = "\n".join(f"- {t}: {json.dumps(s, separators=(',', ':'))}" for t, s in sorted(library.items()))
    return [
        {
            "name": "show_component",
            "description": (
                "Show a live component from the GenUI library in the chat, at the start of a task and before "
                "the long work; then keep it current with update_component. props must validate against the "
                "type's JSON Schema below: invalid props are not shown and come back as errors to fix. Returns "
                "{\"ok\": true, \"directive\": ...}: put the directive line alone, as its own paragraph, in your "
                "next reply text. One component per entity: show it once, never again.\n"
                f"Library (type: props JSON Schema):\n{catalog}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Your id for this entity, e.g. \"pr\". Reuse it in update_component."},
                    "type": {"type": "string", "enum": types},
                    "props": {"type": "object", "description": "The component's props, valid against its schema."},
                },
                "required": ["id", "type", "props"],
                "additionalProperties": False,
            },
        },
        {
            "name": "update_component",
            "description": (
                "Update a shown component in place with a JSON Merge Patch (RFC 7386) on its current props: "
                "keys you send replace theirs, null removes a key, and arrays (commits, checks, actions) are "
                "replaced whole, so send the full array. The result is validated again: an invalid patch "
                "changes nothing and returns errors. Call it after every tool result that changes what the "
                "user should see, before the next tool call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The id given to show_component."},
                    "patch": {"type": "object", "description": "JSON Merge Patch on the props."},
                },
                "required": ["id", "patch"],
                "additionalProperties": False,
            },
        },
        {
            "name": "ask_user",
            "description": (
                "Ask the user a plain-text question when no component helps (never for a decision a "
                "component's actions can carry). Then end your turn: the answer comes back as the user's "
                "next message."
            ),
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
                "additionalProperties": False,
            },
        },
    ]
