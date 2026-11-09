# GenUI benchmark v3: living components

Measures whether an agent shows the right component (or none) early, keeps it current while it works,
asks only for consequential decisions, and acts on exactly what the user chose. Inspired by Phil
Pitus' "Generative UI #2: Merge conflicts" demo.

## Design

Every task follows the same rules:

- **A natural request that never mentions a UI.** The agent decides to show a component, which one, or none.
- **A scripted world** (`genui3/world.py`): domain tools return scripted results, and those results are
  the only truth. A card may not show a state no result has confirmed.
- **Consent enforced by the world.** A risky tool refuses to run without the user's click, and acts only
  on what that click selected (`requires_user_action` with a `scope`).
- **Decisions only where they matter**, with their reason, and gone from the card once answered.
- **A variant where the world diverges** (checks fail, a migration breaks, a file is in use), so the
  agent must react to results rather than follow a script.
- **Negative controls**, where the right UI is none.

## Tasks

| Family | Component | Tasks |
|---|---|---|
| Pull request | `pr_card` | `pr_merge_conflicts`, `pr_checks_fail` |
| Release, machine | `task_card` | `deploy_release`, `deploy_migration_fails`, `workstation_freeze` |
| Review before deleting | `review_list` | `downloads_cleanup`, `downloads_file_in_use`, `prune_branches` |
| Negative controls | none | `neg_pass_formula`, `neg_cli_command`, `neg_hello_file` |

`build_tasks.py` writes `tasks_v3.jsonl`. `library/<type>.schema.json` mirrors the plugin's component
schemas; the cards are drawn by the plugin's own themes (`plugin/themes/`), so what users see is what
is graded.

## Graders (`genui3/grader.py`)

component_choice or no_component, props_valid, single_living_card, zero_render_errors, early_feedback,
live_progress, status_sequence, grounded:* (no state shown before a tool result proves it),
decision_gating, decision_offered:*, never_offers:*, minimal_interruptions, decision_cleared,
text:* (explanations, no stale question), effect:* (what the agent did in the world, e.g. deleted
exactly the user's selection), answer:* (negative controls), final:*, closes_loop.

## Run

```sh
python benchmark/build_tasks.py                    # rebuild tasks_v3.jsonl
python benchmark/run_eval.py --agent reference     # 100 %: hand-written policies, one per family
python benchmark/run_eval.py --agent silent        # 0 %: works with no UI, never asks, claims success
python benchmark/run_eval.py --agent hermes_adapter:HermesAgent --screens
GENUI_ARM=baseline python benchmark/run_eval.py --agent hermes_adapter:HermesAgent
```

`hermes_adapter.HermesAgent` sends the plugin's own turn hint and tool schemas to the model Hermes runs
(`HERMES_MODEL`, with `ANTHROPIC_API_KEY` in `.env`). `GENUI_ARM=baseline` is Hermes without the plugin:
the task's tools plus a plain question tool, and no hint. Results, traces and screenshots go to
`benchmark/results/`. Other options: `--task <ids>`, `--theme <name>`, `--themes <dir>`.

## Validity

`tests/test_bench.py` checks that the reference agent passes every task, and runs one mutant per
grader (the reference with one deliberate fault, such as deleting its own pick instead of the user's
selection, or deploying without asking) to prove the grader catches it.

## Simulated user (`genui3/sim.py`)

When the agent ends its turn, the user may fill the card's fields and click one offered action, as
scripted per task: `{"click": "<regex>", "set": {"selected": ["<regex>", ...]}}`. The click comes back
as `{"type": "user_action", "component_id", "action_id", "values"}`.
