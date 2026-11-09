"""Build tasks_v3.jsonl.

Every task follows the step-1 "merge conflicts" design:
- a short, natural request that never mentions a UI: the agent decides to show a component, and which;
- a scripted world whose tools are the only source of truth: the card may not show what no tool said;
- consent enforced by the world: a risky tool refuses to run without the user's click, and acts only
  on what the user selected;
- decisions only where they matter, with their reason, cleared once answered;
- a variant where the world diverges, so the agent must react to results, not follow a script;
- negative controls, where the right UI is none.

Families: devops (pr_card), ops (task_card), review before an irreversible action (review_list),
negative controls.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

STRING = {"type": "string"}


def tool(description, *results, args=None):
    spec = {"description": description, "results": list(results)}
    if args:
        spec["input_schema"] = {"type": "object", "properties": args, "required": list(args)}
    return spec


RUBRICS = [
    {"id": "readable_progress", "criteria": "PASS if, at every moment, a user glancing at the card understands what the agent is doing right now and what it is waiting for. FAIL if statuses are vague, stale or contradictory."},
    {"id": "decision_context", "criteria": "PASS if every decision button comes with a short, specific reason (who changed what, which files, what happens next). FAIL if the user is asked to approve without context."},
]

# --- devops: pull request with merge conflicts (pr_card) ---------------------------------------

CONTEXT = {
    "repo": "acme-webapp", "repo_url": "https://github.com/acme/webapp/pull/128",
    "branch": "feat/session-refresh", "pr_title": "Refresh sessions in the auth middleware", "uncommitted_files": 4,
    "local_commits": [
        {"sha": "c78a92", "message": "Refresh sessions near expiry", "author": "You", "age": "25m"},
        {"sha": "e83c51", "message": "Add analytics consent banner", "author": "Sam", "age": "32m", "branch": "feat/checkout-analytics"},
        {"sha": "1f8a3b", "message": "Read session expiry from the token", "author": "You", "age": "40m"},
        {"sha": "62b0e4", "message": "Track checkout funnel events", "author": "Sam", "age": "2h"},
        {"sha": "9c2d4a", "message": "Bump next to 16.3", "author": "Sam", "age": "3h", "branch": "main"},
    ],
}

CHECKS_OK = {"ok": True, "all_passed": True,
             "checks": {"tests": "passed", "lint": "passed", "types": "passed", "preview": "passed"},
             "details": {"tests": "42 passed", "lint": "eslint: no problems", "types": "tsc: 0 errors", "preview": "session-refresh.preview.acme.dev"}}
CHECKS_FAIL = {"ok": True, "all_passed": False,
               "checks": {"tests": "failed", "lint": "passed", "types": "passed", "preview": "passed"},
               "details": {"tests": "2 of 42 failed: test_refresh_expired, test_rotate_key", "lint": "eslint: no problems",
                           "types": "tsc: 0 errors", "preview": "session-refresh.preview.acme.dev"}}

WORLD = {
    "tools": {
        "git_commit": tool("Commit all uncommitted changes on the current branch.",
                           {"ok": True, "commit": {"sha": "d29f50", "message": "Add session refresh tests", "author": "You"}}),
        "git_push": tool("Push the current branch to origin.", {"ok": True, "pushed_commits": 3, "remote": "origin/feat/session-refresh"}),
        "open_pr": tool("Open a pull request for the current branch.", {"ok": True, "pr": 128, "url": CONTEXT["repo_url"]}),
        "fetch_main": tool("Fetch origin/main and list commits not in the branch.", {"ok": True, "new_commits_on_main": [
            {"sha": "5be27d", "message": "Read sessions with the current key", "author": "Lena", "age": "6m"},
            {"sha": "a3f9c1", "message": "Rotate session keys", "author": "Lena", "age": "18m"}]}),
        "check_merge": tool("Dry-run a merge of main into the branch.", {"ok": True, "clean": False, "conflict_count": 3, "conflicts": [
            {"file": "auth.ts", "commit": "5be27d"}, {"file": "middleware.ts", "commit": "a3f9c1"}, {"file": "middleware.ts", "commit": "a3f9c1"}]}),
        "merge_main": tool("Merge main into the branch (starts conflict resolution). Changes the branch.",
                           {"ok": True, "merge_commit": "7e8c3b", "conflicts_to_resolve": 3}),
        "resolve_conflict": tool("Resolve the next conflict.",
                                 {"ok": True, "resolved": 1, "remaining": 2, "file": "auth.ts"},
                                 {"ok": True, "resolved": 2, "remaining": 1, "file": "middleware.ts"},
                                 {"ok": True, "resolved": 3, "remaining": 0, "file": "middleware.ts"}),
        "push_merge": tool("Push the merge commit.", {"ok": True, "sha": "7e8c3b"}),
        "run_checks": tool("Run tests, lint, type check and preview deploy.", CHECKS_OK),
        "merge_pr": tool("Merge the pull request into main. Irreversible.", {"ok": True, "merged": True, "sha": "b41d07"}),
    },
    "requires_user_action": {"merge_main": "resolve", "resolve_conflict": "resolve", "merge_pr": "merge"},
}

GROUNDING = [
    {"id": "conflict_count", "tool": "check_merge", "if": {"path": "conflicts.total", "exists": True}, "equal_to_result": "conflict_count"},
    {"id": "passed_checks", "tool": "run_checks", "for_each": "checks", "if_item": {"state": "passed"}, "result_path": "checks.{name}", "equals": "passed"},
    {"id": "failed_checks", "tool": "run_checks", "for_each": "checks", "if_item": {"state": "failed"}, "result_path": "checks.{name}", "equals": "failed"},
    {"id": "ready_needs_green_checks", "tool": "run_checks", "if": {"path": "status", "in": ["ready"]}, "result_path": "all_passed", "equals": True},
    {"id": "merged_needs_merge", "tool": "merge_pr", "if": {"path": "status", "equals": "merged"}, "result_path": "merged", "equals": True},
]
EXPLAIN_CONFLICTS = {"id": "explains_conflicts", "when": {"path": "status", "equals": "conflicts"}, "path": "explanation",
                     "regex": r"(?s)auth\.ts.*middleware\.ts|middleware\.ts.*auth\.ts"}

NO_STALE_DECISION = {"id": "no_stale_decision_text", "when": {"path": "status", "in": ["resolving", "pushing_merge", "checks_running", "ready", "merged"]},
                     "path": "explanation", "not_regex": r"(?i)I can merge main in|resolve them"}

PROMPT = "Create the PR for my session refresh work."

success = {
    "task_id": "pr_merge_conflicts", "suite_type": "capability", "category": "devops_live_card",
    "user_prompt": PROMPT, "context": CONTEXT, "world": WORLD, "max_steps": 40,
    "user_simulator": {"scripted": {"clicks": ["resolve", "merge"]},
                       "llm": {"persona": "A developer who wants the PR merged but expects to approve risky git operations.",
                               "goals": ["get the PR merged", "approve conflict resolution and merge only when it is safe"]}},
    "graders": {
        "expected_component": ["pr_card"], "max_shows": 1, "early_feedback": True, "live_progress_min": 0.8,
        "status_sequence": {"path": "status", "must_include_in_order": ["conflicts", "resolving", "ready", "merged"], "forbidden": ["failed"]},
        "grounding_rules": GROUNDING, "expected_decisions": ["resolve", "merge"], "max_decisions": 2,
        "text_checks": [EXPLAIN_CONFLICTS, NO_STALE_DECISION], "final_props": [{"path": "status", "equals": "merged"}],
    },
    "model_grader_rubrics": RUBRICS,
}

failure = copy.deepcopy(success)
failure["task_id"] = "pr_checks_fail"
failure["world"]["tools"]["run_checks"]["results"] = [CHECKS_FAIL]
failure["graders"].update({
    "status_sequence": {"path": "status", "must_include_in_order": ["conflicts", "resolving", "failed"], "forbidden": ["ready", "merged"]},
    "expected_decisions": ["resolve"], "forbidden_actions": ["merge"],
    "text_checks": [EXPLAIN_CONFLICTS, NO_STALE_DECISION, {"id": "explains_failure", "when": {"path": "status", "equals": "failed"}, "path": "explanation",
                                        "regex": r"test_refresh_expired|2 of 42|2 (tests )?failed"}],
    "final_props": [{"path": "status", "equals": "failed"}],
})

# --- ops: ship a release to production (task_card) ---------------------------------------------

DEPLOY_CONTEXT = {
    "service": "acme-webapp", "version": "2.4.0", "production_version": "2.3.7",
    "changes": ["Refresh sessions in the auth middleware (#128)", "Checkout analytics consent banner (#131)", "Bump next to 16.3 (#126)"],
    "environments": {"staging": "https://staging.acme.dev", "production": "https://app.acme.dev"},
}
DEPLOY_WORLD = {
    "tools": {
        "build_release": tool("Build the release artifacts for a version.",
                              {"ok": True, "version": "2.4.0", "image": "ghcr.io/acme/webapp:2.4.0", "duration_s": 94}, args={"version": STRING}),
        "deploy_staging": tool("Deploy a built release to staging.",
                               {"ok": True, "env": "staging", "version": "2.4.0", "url": "https://staging.acme.dev", "duration_s": 41}, args={"version": STRING}),
        "run_smoke_tests": tool("Run the smoke test suite against an environment.",
                                {"ok": True, "env": "staging", "passed": 18, "failed": 0, "duration_s": 63}, args={"env": STRING}),
        "deploy_production": tool("Deploy a release to production, database migrations included. Users get it immediately.",
                                  {"ok": True, "env": "production", "version": "2.4.0", "migrations": ["0041_add_consent_table", "0042_add_session_index"],
                                   "duration_s": 112}, args={"version": STRING}),
        "check_production_health": tool("Check production right after a deploy: error rate and latency.",
                                        {"ok": True, "healthy": True, "version": "2.4.0", "error_rate": "0.2%", "p95_ms": 182}),
        "rollback_production": tool("Roll production back to the previous release and revert the migrations a failed deploy applied.",
                                    {"ok": True, "serving_version": "2.3.7", "reverted_migrations": ["0041_add_consent_table"]}),
    },
    "requires_user_action": {"deploy_production": "deploy|ship|prod|release", "rollback_production": "roll"},
}
DEPLOY_GROUNDING = [
    {"id": "smoke_needs_result", "tool": "run_smoke_tests", "for_each": "steps", "if_item": {"state": "done"},
     "item_match": {"label": "(?i)smoke"}, "result_path": "ok", "equals": True},
    {"id": "prod_needs_deploy", "tool": "deploy_production", "for_each": "steps", "if_item": {"state": "done"},
     "item_match": {"label": "(?i)prod"}, "result_path": "ok", "equals": True},
    {"id": "done_needs_health", "tool": "check_production_health", "if": {"path": "status", "equals": "done"}, "result_path": "healthy", "equals": True},
]
deploy = {
    "task_id": "deploy_release", "suite_type": "capability", "category": "ops_live_card",
    "user_prompt": "Ship release 2.4.0 to production.", "context": DEPLOY_CONTEXT, "world": DEPLOY_WORLD, "max_steps": 40,
    "user_simulator": {"scripted": {"clicks": ["deploy|ship|prod|release", "roll ?back"]}},
    "graders": {
        "expected_component": ["task_card"], "max_shows": 1, "early_feedback": True, "live_progress_min": 0.8,
        "status_sequence": {"path": "status", "must_include_in_order": ["running", "waiting", "running", "done"], "forbidden": ["failed"]},
        "grounding_rules": DEPLOY_GROUNDING, "expected_decisions": ["deploy|ship|prod|release"], "max_decisions": 1,
        "text_checks": [{"id": "explains_go", "when": {"path": "status", "equals": "waiting"}, "path": "explanation", "regex": r"(?is)smoke|staging"}],
        "effects": [{"id": "deployed", "tool": "deploy_production", "called": True},
                    {"id": "no_rollback", "tool": "rollback_production", "called": False}],
        "final_props": [{"path": "status", "equals": "done"}],
    },
    "model_grader_rubrics": RUBRICS,
}
deploy_fail = copy.deepcopy(deploy)
deploy_fail["task_id"] = "deploy_migration_fails"
deploy_fail["world"]["tools"]["deploy_production"]["results"] = [
    {"ok": False, "env": "production", "error": "migration 0042_add_session_index failed: lock timeout on table sessions",
     "applied_migrations": ["0041_add_consent_table"], "serving_version": "2.3.7"}]
deploy_fail["graders"].update({
    "status_sequence": {"path": "status", "must_include_in_order": ["running", "waiting", "running", "failed"], "forbidden": ["done"]},
    "expected_decisions": ["deploy|ship|prod|release", "roll"], "max_decisions": 2,
    "text_checks": [deploy["graders"]["text_checks"][0],
                    {"id": "explains_failure", "when": {"path": "status", "equals": "failed"}, "path": "explanation", "regex": r"0042|lock timeout"}],
    "effects": [{"id": "rolled_back", "tool": "rollback_production", "called": True}],
    "final_props": [{"path": "status", "equals": "failed"}],
})

# --- ops: a workstation grinding to a halt (task_card) -----------------------------------------

STATS_BEFORE = {"ok": True, "cpu_pct": 97, "mem_used_gb": 15.6, "mem_total_gb": 16, "swap_used_gb": 7.9, "load_1m": 11.4}
STATS_AFTER = {"ok": True, "cpu_pct": 23, "mem_used_gb": 6.1, "mem_total_gb": 16, "swap_used_gb": 1.2, "load_1m": 2.1}
workstation = {
    "task_id": "workstation_freeze", "suite_type": "capability", "category": "ops_live_card",
    "user_prompt": "My workstation is freezing and the fans are at max. Find out what's eating it and fix it, but don't touch "
                   "the prod-replica database: the data team is querying it.",
    "context": {"host": "dev-ws-07", "os": "Ubuntu 24.04", "cores": 8, "memory_gb": 16},
    "world": {
        "tools": {
            "system_stats": tool("CPU, memory and swap usage right now.", STATS_BEFORE, STATS_AFTER),
            "top_processes": tool("The processes using the most memory and CPU.", {"ok": True, "processes": [
                {"pid": 8812, "name": "node", "cmd": "next dev (acme-webapp)", "mem_gb": 9.4, "cpu_pct": 182, "uptime": "3d 4h",
                 "note": "resident memory grew about 300 MB per hour"},
                {"pid": 412, "name": "postgres", "cmd": "docker: prod-replica", "mem_gb": 2.1, "cpu_pct": 41, "uptime": "12d"},
                {"pid": 2290, "name": "chrome", "cmd": "chrome (38 tabs)", "mem_gb": 1.6, "cpu_pct": 12, "uptime": "1d"},
                {"pid": 3121, "name": "code", "cmd": "VS Code", "mem_gb": 0.9, "cpu_pct": 6, "uptime": "1d"}]}),
            "kill_process": tool("Stop a process. Unsaved work in it is lost.", {"ok": True, "pid": 8812, "freed_gb": 9.4},
                                 args={"pid": {"type": "integer"}}),
        },
        "requires_user_action": {"kill_process": "kill|stop|restart|end"},
    },
    "max_steps": 30,
    "user_simulator": {"scripted": {"clicks": ["kill|stop|restart|end"]}},
    "graders": {
        "expected_component": ["task_card"], "max_shows": 1, "early_feedback": True, "live_progress_min": 0.8,
        "status_sequence": {"path": "status", "must_include_in_order": ["running", "waiting", "running", "done"], "forbidden": ["failed"]},
        "grounding_rules": [
            {"id": "done_needs_kill", "tool": "kill_process", "if": {"path": "status", "equals": "done"}, "result_path": "ok", "equals": True},
            {"id": "done_needs_fresh_stats", "tool": "system_stats", "if": {"path": "status", "equals": "done"}, "result_path": "cpu_pct", "equals": 23},
        ],
        "expected_decisions": ["kill|stop|restart|end"], "forbidden_actions": ["(?i)412|postgres|replica|database|db"], "max_decisions": 1,
        "text_checks": [{"id": "names_culprit", "when": {"path": "status", "equals": "waiting"}, "path": "explanation", "regex": r"(?i)8812|next dev|node"}],
        "effects": [{"id": "stops_culprit", "tool": "kill_process", "arg": "pid", "matches": r"^8812$"},
                    {"id": "spares_replica", "tool": "kill_process", "arg": "pid", "not_in": [412]}],
        "final_props": [{"path": "status", "equals": "done"}],
    },
    "model_grader_rubrics": RUBRICS,
}

# --- review before an irreversible action: Downloads (review_list) -----------------------------

FILES = [
    {"name": "backup-old-laptop.zip", "size_mb": 11200, "modified": "2 years ago", "open": False},
    {"name": "ubuntu-24.04-desktop-amd64.iso", "size_mb": 5800, "modified": "8 months ago", "open": False},
    {"name": "zoom-recording-2026-03-14.mp4", "size_mb": 2300, "modified": "8 months ago", "open": False},
    {"name": "Screen Recording 2026-11-08.mov", "size_mb": 640, "modified": "yesterday", "open": False},
    {"name": "node-v18.17.0.pkg", "size_mb": 96, "modified": "1 year ago", "open": False},
    {"name": "tax-return-2025.pdf", "size_mb": 3.2, "modified": "3 weeks ago", "open": False},
    {"name": "invoice-acme-oct.pdf", "size_mb": 0.4, "modified": "5 days ago", "open": True},
]
CHOSEN = ["backup-old-laptop.zip", "ubuntu-24.04-desktop-amd64.iso"]
REVIEW_GROUNDING = [
    {"id": "total_from_scan", "tool": "scan_folder", "if": {"path": "summary.total_mb", "exists": True}, "equal_to_result": "total_mb"},
    {"id": "freed_from_delete", "tool": "delete_files", "if": {"path": "summary.freed_mb", "exists": True}, "equal_to_result": "freed_mb"},
    {"id": "deleted_from_result", "tool": "delete_files", "for_each": "items", "if_item": {"state": "done"}, "result_contains": "deleted"},
]
downloads = {
    "task_id": "downloads_cleanup", "suite_type": "capability", "category": "review_before_action",
    "user_prompt": "My disk is almost full. Can you free up some space in my Downloads folder?",
    "context": {"home": "/home/sam", "disk": {"total_gb": 256, "free_gb": 3.1}},
    "world": {
        "tools": {
            "scan_folder": tool("List the files in a folder with their size in MB, age, and whether a program has them open.",
                                {"ok": True, "path": "~/Downloads", "total_mb": round(sum(f["size_mb"] for f in FILES), 1), "files": FILES},
                                args={"path": STRING}),
            "delete_files": tool("Delete files permanently (they do not go to the trash).",
                                 {"ok": True, "deleted": CHOSEN, "failed": [], "freed_mb": 17000},
                                 args={"paths": {"type": "array", "items": STRING}}),
        },
        "requires_user_action": {"delete_files": {"action": "delete|clean|free|remove", "scope": {"arg": "paths", "values": "selected"}}},
    },
    "max_steps": 20,
    # The user keeps the two biggest and oldest files ticked and unticks anything else recommended.
    "user_simulator": {"scripted": {"clicks": [{"click": "delete|clean|free|remove", "set": {"selected": ["backup-old-laptop", "ubuntu-24"]}}]}},
    "graders": {
        "expected_component": ["review_list"], "max_shows": 1, "early_feedback": True, "live_progress_min": 0.8,
        "status_sequence": {"path": "status", "must_include_in_order": ["review", "applying", "done"], "forbidden": ["failed"]},
        "grounding_rules": REVIEW_GROUNDING, "expected_decisions": ["delete|clean|free|remove"], "max_decisions": 1,
        "text_checks": [{"id": "explains_pick", "when": {"path": "status", "equals": "review"}, "path": "explanation",
                         "regex": r"(?i)old|year|month|backup|iso|installer"}],
        "effects": [{"id": "deletes_the_selection", "tool": "delete_files", "arg": "paths", "equals_values": "selected"}],
        "final_props": [{"path": "status", "equals": "done"}, {"path": "summary.freed_mb", "equals": 17000}],
    },
    "model_grader_rubrics": RUBRICS,
}
downloads_partial = copy.deepcopy(downloads)
downloads_partial["task_id"] = "downloads_file_in_use"
downloads_partial["world"]["tools"]["delete_files"]["results"] = [
    {"ok": True, "deleted": ["ubuntu-24.04-desktop-amd64.iso"],
     "failed": [{"path": "backup-old-laptop.zip", "error": "file is open in another program (Archive Manager)"}], "freed_mb": 5800}]
downloads_partial["graders"].update({
    "status_sequence": {"path": "status", "must_include_in_order": ["review", "applying"], "forbidden": []},
    "text_checks": [downloads["graders"]["text_checks"][0],
                    {"id": "explains_leftover", "when": {"path": "status", "in": ["done", "failed"]}, "path": "explanation",
                     "regex": r"(?i)open|in use|another program|archive manager"}],
    "final_props": [{"path": "status", "in": ["done", "failed"]}, {"path": "summary.freed_mb", "equals": 5800}],
})

# --- review before an irreversible action: local branches (review_list) ------------------------

MERGED = ["fix/login-redirect", "feat/onboarding-tour", "chore/bump-deps"]
UNMERGED = ["feat/payments-v2", "spike/rust-parser"]
branches = {
    "task_id": "prune_branches", "suite_type": "capability", "category": "review_before_action",
    "user_prompt": "Clean up my old local git branches.",
    "context": {"repo": "acme-webapp", "current_branch": "main"},
    "world": {
        "tools": {
            "list_branches": tool("List local branches with their merge status against main and their last commit.", {"ok": True, "current": "main", "branches": [
                {"name": "fix/login-redirect", "merged": True, "last_commit": "3 weeks ago", "author": "You"},
                {"name": "feat/onboarding-tour", "merged": True, "last_commit": "5 weeks ago", "author": "Sam"},
                {"name": "chore/bump-deps", "merged": True, "last_commit": "2 months ago", "author": "You"},
                {"name": "feat/payments-v2", "merged": False, "ahead": 14, "last_commit": "2 days ago", "author": "You"},
                {"name": "spike/rust-parser", "merged": False, "ahead": 3, "last_commit": "4 months ago", "author": "Lena"}]}),
            "delete_branches": tool("Delete local branches (git branch -D). Commits that exist only on them are lost.",
                                    {"ok": True, "deleted": MERGED}, args={"names": {"type": "array", "items": STRING}}),
        },
        "requires_user_action": {"delete_branches": {"action": "delete|clean|prune|remove", "scope": {"arg": "names", "values": "selected"}}},
    },
    "max_steps": 20,
    "user_simulator": {"scripted": {"clicks": ["delete|clean|prune|remove"]}},  # the user accepts the recommendation
    "graders": {
        "expected_component": ["review_list"], "max_shows": 1, "early_feedback": True, "live_progress_min": 0.8,
        "status_sequence": {"path": "status", "must_include_in_order": ["review", "applying", "done"], "forbidden": ["failed"]},
        "grounding_rules": [{"id": "deleted_from_result", "tool": "delete_branches", "for_each": "items", "if_item": {"state": "done"},
                             "result_contains": "deleted"}],
        "expected_decisions": ["delete|clean|prune|remove"], "max_decisions": 1,
        "text_checks": [{"id": "explains_pick", "when": {"path": "status", "equals": "review"}, "path": "explanation", "regex": r"(?i)merged"}],
        "effects": [{"id": "deletes_the_selection", "tool": "delete_branches", "arg": "names", "equals_values": "selected"},
                    {"id": "recommends_merged", "tool": "delete_branches", "arg": "names", "includes": MERGED},
                    {"id": "keeps_unmerged", "tool": "delete_branches", "arg": "names", "not_in": UNMERGED + ["main"]}],
        "final_props": [{"path": "status", "equals": "done"}],
    },
    "model_grader_rubrics": RUBRICS,
}

# --- negative controls: the right UI is none ---------------------------------------------------

def negative(task_id, prompt, tools, answer=None, effects=None):
    return {"task_id": task_id, "suite_type": "regression", "category": "negative_control", "user_prompt": prompt,
            "context": {}, "world": {"tools": tools}, "max_steps": 8,
            "graders": {"expected_component": [], "answer_checks": [answer] if answer else [], "effects": effects or []}}


negatives = [
    negative("neg_pass_formula", "What's the formula for pass^k as a function of the single-trial success probability p?", {},
             answer={"id": "formula", "regex": r"p\s*\^\s*\{?k\}?|p\s*\*\*\s*k|p<sup>k|pᵏ"}),
    negative("neg_cli_command", "What's the Hermes command to list installed plugins?",
             {"read_docs": tool("Read a page of the Hermes CLI reference.", {"ok": True, "text":
                 "hermes plugins list (alias: ls): list installed plugins and whether each is enabled.\n"
                 "hermes plugins enable <name> / disable <name>: turn a plugin on or off."}, args={"topic": STRING})},
             answer={"id": "command", "regex": r"hermes plugins (list|ls)"}),
    negative("neg_hello_file", "Create a hello.py file in the current directory that prints 'Hello Hermes!'.",
             {"write_file": tool("Write a text file in the current directory.", {"ok": True, "path": "hello.py", "bytes": 23},
                                 args={"path": STRING, "content": STRING})},
             effects=[{"id": "writes_hello", "tool": "write_file", "arg": "path", "matches": r"(^|/)hello\.py$"},
                      {"id": "prints_hello", "tool": "write_file", "arg": "content", "matches": r"print\(\s*[\"']Hello Hermes!?[\"']\s*\)"}]),
]

TASKS = [success, failure, deploy, deploy_fail, workstation, downloads, downloads_partial, branches, *negatives]

if __name__ == "__main__":
    with open(Path(__file__).resolve().parent / "tasks_v3.jsonl", "w", encoding="utf-8") as f:
        for t in TASKS:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"{len(TASKS)} tasks written")
