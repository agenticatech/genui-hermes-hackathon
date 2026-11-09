"""Agents used to validate the v3 tasks: a task is valid when the reference scores 100 % and the
silent agent fails it.

ReferenceAgent    picks the hand-written policy for the task's family. Each behaves like the demo:
                  show the card first, update it after every tool result, ask only before the risky
                  step, act on exactly what the user chose, never claim a state no tool has confirmed.
                  They react to results, so they handle every variant of their family.
  PRReferenceAgent, DeployReferenceAgent, WorkstationReferenceAgent, ReviewReferenceAgent,
  NegativeReferenceAgent
SilentAgentRouter the "big block" behaviour: works with no UI and never asks, then claims success
  SilentAgent (pull requests: dumps one final card), NoUIAgent (every other family)
YourAgent         adapter template for the real Hermes agent.
"""
from __future__ import annotations

from .runner import UI_TOOLS, AgentStep


def _ui(tool, **args):
    return {"tool": tool, "args": args}


def _call(tool, **args):
    return {"tool": tool, "args": args}


class PRReferenceAgent:
    def reset(self, task: dict, tools: list[dict]) -> None:
        self.ctx, self.started, self.commits = None, False, []

    def _upd(self, **patch):
        return _ui("update_component", id="pr", patch=patch)

    def step(self, obs: list[dict]) -> AgentStep:
        for o in obs:
            if o["type"] == "user_message":
                self.ctx = o["context"]
                self.commits = [{**c, "state": "ok"} for c in self.ctx["local_commits"]]
                return AgentStep(tool_calls=[
                    _ui("show_component", id="pr", type="pr_card", props={
                        "title": self.ctx["pr_title"], "pr": None, "status": "committing",
                        "status_text": f"Committing {self.ctx['uncommitted_files']} changed files",
                        "commits": [{"sha": "-", "message": "Uncommitted changes", "author": "You", "branch": self.ctx["branch"], "state": "pending"}] + self.commits}),
                    _call("git_commit")])
            if o["type"] == "user_action":
                if o["action_id"] == "resolve_conflicts":
                    # explanation=None removes the key (JSON Merge Patch): the question has been answered.
                    return AgentStep(tool_calls=[self._upd(status="resolving", status_text="Merging main into the branch", actions=[], explanation=None),
                                                 _call("merge_main")])
                if o["action_id"] == "merge_pr":
                    return AgentStep(tool_calls=[self._upd(status_text="Merging into main", actions=[]), _call("merge_pr")])
            if o["type"] != "tool_result" or o["tool"] in ("show_component", "update_component"):
                continue
            r, t = o["result"], o["tool"]
            if t == "git_commit":
                c = r["commit"]
                self.commits = [{"sha": c["sha"], "message": c["message"], "author": c["author"], "branch": self.ctx["branch"], "age": "now", "state": "new"}] + self.commits
                return AgentStep(tool_calls=[self._upd(status="pushing", status_text="Pushing commits to origin", commits=self.commits), _call("git_push")])
            if t == "git_push":
                return AgentStep(tool_calls=[self._upd(status="opening_pr", status_text=f"Pushed {r['pushed_commits']} commits, opening the PR"), _call("open_pr")])
            if t == "open_pr":
                return AgentStep(tool_calls=[self._upd(pr=r["pr"], status="fetching", status_text="Fetching main"), _call("fetch_main")])
            if t == "fetch_main":
                main = [{**c, "branch": "main", "state": "pending"} for c in r["new_commits_on_main"]]
                self.commits = self.commits[:1] + main + self.commits[1:]
                return AgentStep(tool_calls=[self._upd(status="checking_merge", status_text="Checking it merges cleanly", commits=self.commits), _call("check_merge")])
            if t == "check_merge":
                if r["clean"]:
                    return AgentStep(tool_calls=[self._upd(status="checks_running", status_text="Running checks"), _call("run_checks")])
                bad = {c["commit"] for c in r["conflicts"]}
                files = sorted({c["file"] for c in r["conflicts"]})
                self.commits = [{**c, "state": "conflict" if c["sha"] in bad else c["state"]} for c in self.commits]
                authors = sorted({c["author"] for c in self.commits if c["sha"] in bad})
                return AgentStep(text="", tool_calls=[self._upd(
                    status="conflicts", status_text=f"{r['conflict_count']} conflicts with main", commits=self.commits,
                    conflicts={"total": r["conflict_count"], "resolved": 0, "files": files},
                    explanation=f"PR is open, but main moved on while we worked: {' and '.join(authors)}'s commits changed the same lines in "
                                f"{' and '.join(files)}. I can merge main in and resolve them.",
                    actions=[{"id": "resolve_conflicts", "label": "Resolve conflicts", "kind": "primary"}])])
            if t in ("merge_main", "resolve_conflict"):
                if t == "resolve_conflict":
                    done = r["resolved"]
                    self.commits = [{**c, "state": "resolved"} if c["state"] == "conflict" and r["remaining"] == 0 else c for c in self.commits]
                    total = done + r["remaining"]
                    if r["remaining"]:
                        return AgentStep(tool_calls=[self._upd(status_text=f"Resolving conflict {done + 1} of {total}", conflicts={"resolved": done}), _call("resolve_conflict")])
                    return AgentStep(tool_calls=[self._upd(status="pushing_merge", status_text="Pushing the merge", conflicts={"resolved": done}, commits=self.commits), _call("push_merge")])
                return AgentStep(tool_calls=[self._upd(status_text=f"Resolving conflict 1 of {r['conflicts_to_resolve']}"), _call("resolve_conflict")])
            if t == "push_merge":
                pend = [{"name": n, "state": "running"} for n in ("Tests", "Lint", "Types", "Preview")]
                return AgentStep(tool_calls=[self._upd(status="checks_running", status_text="Running checks", checks=pend), _call("run_checks")])
            if t == "run_checks":
                checks = [{"name": n.capitalize(), "state": s, "detail": r["details"][n]} for n, s in r["checks"].items()]
                if r["all_passed"]:
                    return AgentStep(tool_calls=[self._upd(status="ready", status_text="Ready to merge", checks=checks,
                                                           actions=[{"id": "merge_pr", "label": "Merge", "kind": "primary"}])])
                failed = [f"{n}: {r['details'][n]}" for n, s in r["checks"].items() if s == "failed"]
                return AgentStep(tool_calls=[self._upd(status="failed", status_text="Checks failed, not merging", checks=checks,
                                                       explanation="Conflicts are resolved and pushed, but " + "; ".join(failed) + ". I will not merge until they pass.",
                                                       actions=[{"id": "fix_tests", "label": "Fix failing tests", "kind": "primary"}])])
            if t == "merge_pr" and r.get("merged"):
                return AgentStep(text="Merged.", tool_calls=[self._upd(status="merged", status_text="Merged into main", actions=[],
                                                                      links=[{"label": "GitHub", "url": self.ctx["repo_url"]}])])
        return AgentStep()


class SilentAgent:
    """Works silently, then dumps the final state in one card (and never asks before risky steps)."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.plan = ["git_commit", "git_push", "open_pr", "fetch_main", "check_merge", "merge_main",
                     "resolve_conflict", "resolve_conflict", "resolve_conflict", "push_merge", "run_checks", "merge_pr"]
        self.done, self.ctx = False, None

    def step(self, obs: list[dict]) -> AgentStep:
        if self.ctx is None:
            self.ctx = obs[0]["context"]
            return AgentStep(text="Working on it...", tool_calls=[_call(t) for t in self.plan])
        if self.done:
            return AgentStep()
        self.done = True
        return AgentStep(text="All done: PR created, conflicts resolved, checks run and merged.", tool_calls=[
            _ui("show_component", id="pr", type="pr_card", props={
                "title": self.ctx["pr_title"], "pr": 128, "status": "merged", "status_text": "Merged into main",
                "commits": [{**c, "state": "ok"} for c in self.ctx["local_commits"]],
                "checks": [{"name": n, "state": "passed"} for n in ("Tests", "Lint", "Types", "Preview")]})])


def _world_results(obs: list[dict]):
    return [(o["tool"], o["result"]) for o in obs if o["type"] == "tool_result" and o["tool"] not in UI_TOOLS]


class _Steps:
    """A step list the reference agents patch whole (arrays are replaced whole by a merge patch)."""

    def __init__(self, *steps):
        self.steps = [{"id": i, "label": label, "state": "pending"} for i, label in steps]

    def set(self, sid, state, detail=None):
        for s in self.steps:
            if s["id"] == sid:
                s["state"] = state
                if detail:
                    s["detail"] = detail
        return self.copy()

    def add(self, sid, label, state):
        self.steps.append({"id": sid, "label": label, "state": state})
        return self.copy()

    def copy(self):
        return [dict(s) for s in self.steps]


class DeployReferenceAgent:
    """Ship a release: build, staging, smoke tests without asking; production only on the user's go;
    on a failed deploy, show the real error and offer the rollback."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.ctx, self.failure = None, ""

    def _upd(self, **patch):
        return _ui("update_component", id="release", patch=patch)

    def step(self, obs: list[dict]) -> AgentStep:
        for o in obs:
            if o["type"] == "user_message":
                self.ctx = c = o["context"]
                v = c["version"]
                self.steps = _Steps(("build", f"Build {v}"), ("staging", "Deploy to staging"), ("smoke", "Smoke tests on staging"),
                                    ("prod", "Deploy to production"), ("health", "Production health check"))
                return AgentStep(tool_calls=[
                    _ui("show_component", id="release", type="task_card", props={
                        "title": f"Release {v}", "subtitle": f"{c['service']} · production runs {c['production_version']}",
                        "status": "running", "status_text": f"Building {v}", "steps": self.steps.set("build", "running")}),
                    _call("build_release", version=v)])
            if o["type"] == "user_action":
                v = self.ctx["version"]
                if "roll" in o["action_id"]:
                    steps = self.steps.add("rollback", f"Roll back to {self.ctx['production_version']}", "running")
                    return AgentStep(tool_calls=[self._upd(status="running", status_text="Rolling back production", steps=steps,
                                                           explanation=None, actions=[]), _call("rollback_production")])
                return AgentStep(tool_calls=[self._upd(status="running", status_text=f"Deploying {v} to production",
                                                       steps=self.steps.set("prod", "running"), explanation=None, actions=[]),
                                             _call("deploy_production", version=v)])
        for t, r in _world_results(obs):
            v = self.ctx["version"]
            if t == "build_release":
                self.steps.set("build", "done", f"{r['duration_s']} s")
                return AgentStep(tool_calls=[self._upd(status_text="Deploying to staging", steps=self.steps.set("staging", "running")),
                                             _call("deploy_staging", version=v)])
            if t == "deploy_staging":
                self.steps.set("staging", "done", f"{r['duration_s']} s")
                return AgentStep(tool_calls=[self._upd(status_text="Running smoke tests on staging", steps=self.steps.set("smoke", "running")),
                                             _call("run_smoke_tests", env="staging")])
            if t == "run_smoke_tests":
                return AgentStep(tool_calls=[self._upd(
                    status="waiting", status_text="Waiting for your go", steps=self.steps.set("smoke", "done", f"{r['passed']} passed"),
                    explanation=f"Staging is green: {r['passed']} smoke tests passed on {v}. Deploying runs the database migrations "
                                "and users get the new version at once.",
                    actions=[{"id": "deploy_production", "label": f"Deploy {v} to production", "kind": "primary"}])])
            if t == "deploy_production":
                if r.get("ok"):
                    self.steps.set("prod", "done", f"{len(r['migrations'])} migrations")
                    return AgentStep(tool_calls=[self._upd(status_text="Checking production health", steps=self.steps.set("health", "running")),
                                                 _call("check_production_health")])
                self.failure = r.get("error", "unknown error")
                serving = r.get("serving_version", self.ctx["production_version"])
                applied = ", ".join(r.get("applied_migrations") or []) or "nothing"
                return AgentStep(tool_calls=[self._upd(
                    status="failed", status_text="Production deploy failed", steps=self.steps.set("prod", "failed", self.failure.split(": ")[-1]),
                    explanation=f"{self.failure[0].upper()}{self.failure[1:]}. {applied} is applied while production still serves "
                                f"{serving}: roll back to undo it.",
                    actions=[{"id": "rollback_production", "label": f"Roll back to {serving}", "kind": "danger"}])])
            if t == "rollback_production":
                return AgentStep(tool_calls=[self._upd(
                    status="failed", status_text=f"Rolled back: production serves {r['serving_version']}",
                    steps=self.steps.set("rollback", "done", f"serving {r['serving_version']}"),
                    explanation=f"The {v} deploy failed ({self.failure}). Its migrations were reverted and production serves "
                                f"{r['serving_version']} again.")])
            if t == "check_production_health":
                return AgentStep(tool_calls=[self._upd(
                    status="done", status_text=f"{v} is live", steps=self.steps.set("health", "done", f"p95 {r['p95_ms']} ms"),
                    metrics=[{"label": "error rate", "value": r["error_rate"], "tone": "good"},
                             {"label": "p95 latency", "value": f"{r['p95_ms']} ms", "tone": "good"}])])
        return AgentStep()


class WorkstationReferenceAgent:
    """Diagnose a slow machine live, name the culprit from the process list, stop it only on the user's
    go, never the process the user asked to keep, then check that it recovered."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.ctx, self.stats_seen, self.culprit, self.items = None, 0, None, []

    def _upd(self, **patch):
        return _ui("update_component", id="workstation", patch=patch)

    @staticmethod
    def _metrics(r):
        mem = r["mem_used_gb"] / r["mem_total_gb"]
        return [{"label": "memory", "value": f"{r['mem_used_gb']} / {r['mem_total_gb']} GB", "tone": "bad" if mem > 0.9 else "good"},
                {"label": "CPU", "value": f"{r['cpu_pct']}%", "tone": "bad" if r["cpu_pct"] > 90 else "good"},
                {"label": "swap", "value": f"{r['swap_used_gb']} GB", "tone": "warn" if r["swap_used_gb"] > 2 else "good"}]

    def step(self, obs: list[dict]) -> AgentStep:
        for o in obs:
            if o["type"] == "user_message":
                self.ctx = c = o["context"]
                self.steps = _Steps(("stats", "Measure CPU and memory"), ("procs", "Find the heaviest processes"),
                                    ("fix", "Stop the culprit"), ("verify", "Check that it recovered"))
                return AgentStep(tool_calls=[
                    _ui("show_component", id="workstation", type="task_card", props={
                        "title": f"Why {c['host']} is freezing", "subtitle": f"{c['os']} · {c['cores']} cores · {c['memory_gb']} GB",
                        "status": "running", "status_text": "Measuring CPU and memory", "steps": self.steps.set("stats", "running")}),
                    _call("system_stats")])
            if o["type"] == "user_action":
                p = self.culprit
                return AgentStep(tool_calls=[self._upd(status="running", status_text=f"Stopping {p['name']} (pid {p['pid']})",
                                                       steps=self.steps.set("fix", "running"), explanation=None, actions=[]),
                                             _call("kill_process", pid=p["pid"])])
        for t, r in _world_results(obs):
            if t == "system_stats" and self.stats_seen == 0:
                self.stats_seen = 1
                self.steps.set("stats", "done", f"CPU {r['cpu_pct']}%")
                return AgentStep(tool_calls=[self._upd(status_text="Finding the heaviest processes", metrics=self._metrics(r),
                                                       steps=self.steps.set("procs", "running")), _call("top_processes")])
            if t == "top_processes":
                keep = [p for p in r["processes"] if "replica" in p["cmd"]]
                p = self.culprit = max((p for p in r["processes"] if p not in keep), key=lambda p: p["mem_gb"])
                self.items = [{"id": str(x["pid"]), "label": f"{x['name']} · {x['cmd']}",
                               "detail": f"{x['cpu_pct']}% CPU · up {x['uptime']}" + (" · kept, as you asked" if x in keep else ""),
                               "value": f"{x['mem_gb']} GB", "tone": "bad" if x is p else "neutral"} for x in r["processes"]]
                return AgentStep(tool_calls=[self._upd(
                    status="waiting", status_text="Waiting for your go", items=self.items,
                    steps=self.steps.set("procs", "done", f"{len(r['processes'])} checked"),
                    explanation=f"The {p['cmd']} (node, pid {p['pid']}) holds {p['mem_gb']} GB and its {p.get('note', 'memory keeps growing')}. "
                                "Stopping it frees the memory; unsaved work in it is lost. The prod-replica database is left alone.",
                    actions=[{"id": f"stop_{p['pid']}", "label": f"Stop {p['name']} (pid {p['pid']})", "kind": "danger"}])])
            if t == "kill_process":
                for it in self.items:
                    if it["id"] == str(self.culprit["pid"]):
                        it.update(detail="stopped", tone="neutral")
                return AgentStep(tool_calls=[self._upd(status_text="Checking that it recovered", items=self.items,
                                                       steps=(self.steps.set("fix", "done", f"{r['freed_gb']} GB freed"),
                                                              self.steps.set("verify", "running"))[1]),
                                             _call("system_stats")])
            if t == "system_stats":
                return AgentStep(tool_calls=[self._upd(
                    status="done", status_text=f"Back to normal: {r['mem_used_gb']} / {r['mem_total_gb']} GB used, CPU {r['cpu_pct']}%",
                    metrics=self._metrics(r), steps=self.steps.set("verify", "done", f"CPU {r['cpu_pct']}%"))])
        return AgentStep()


class ReviewReferenceAgent:
    """List what could go, recommend a safe selection, act on exactly what the user ticked, and show
    the real outcome item by item."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.files = any(t["name"] == "scan_folder" for t in tools)
        self.cid = "downloads" if self.files else "branches"
        self.items, self.names = [], {}

    def _upd(self, **patch):
        return _ui("update_component", id=self.cid, patch=patch)

    @staticmethod
    def _gb(mb):
        return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{round(mb)} MB"

    def step(self, obs: list[dict]) -> AgentStep:
        for o in obs:
            if o["type"] == "user_message":
                c = o["context"]
                if self.files:
                    props = {"title": "Free up space in Downloads", "subtitle": f"~/Downloads · {c['disk']['free_gb']} GB free on disk",
                             "status": "scanning", "status_text": "Scanning ~/Downloads", "items": []}
                    first = _call("scan_folder", path="~/Downloads")
                else:
                    props = {"title": "Clean up local branches", "subtitle": f"{c['repo']} · on {c['current_branch']}",
                             "status": "scanning", "status_text": "Listing local branches", "items": []}
                    first = _call("list_branches")
                return AgentStep(tool_calls=[_ui("show_component", id=self.cid, type="review_list", props=props), first])
            if o["type"] == "user_action":
                chosen = list((o.get("values") or {}).get("selected") or [])
                if self.files:
                    work = _call("delete_files", paths=chosen)
                else:
                    work = _call("delete_branches", names=chosen)
                return AgentStep(tool_calls=[self._upd(status="applying", status_text=f"Deleting {len(chosen)} of {len(self.items)}",
                                                       explanation=None, actions=[]), work])
        for t, r in _world_results(obs):
            if t == "scan_folder":
                for f in r["files"]:
                    old = any(w in f["modified"] for w in ("month", "year"))
                    pick = old and not f["open"] and not f["name"].endswith(".pdf")
                    self.items.append({"id": f["name"], "label": f["name"], "detail": f"modified {f['modified']}", "size_mb": f["size_mb"],
                                       "selected": pick, **({"locked": True, "tag": "open", "tone": "warn"} if f["open"] else
                                                            {"tag": "old" if old else "recent", "tone": "neutral"})})
                picked = [i for i in self.items if i["selected"]]
                return AgentStep(tool_calls=[self._upd(
                    status="review", status_text="Pick what to delete", items=self.items, summary={"total_mb": r["total_mb"]},
                    explanation=f"Ticked: {len(picked)} files older than a few months that nothing has open "
                                f"({self._gb(sum(i['size_mb'] for i in picked))}). Recent recordings and documents stay unticked.",
                    actions=[{"id": "delete_selected", "label": "Delete selected", "kind": "danger"}])])
            if t == "list_branches":
                for b in r["branches"]:
                    self.items.append({"id": b["name"], "label": b["name"], "detail": f"{b['author']} · last commit {b['last_commit']}",
                                       "selected": b["merged"], "tag": "merged" if b["merged"] else f"{b['ahead']} unmerged commits",
                                       "tone": "good" if b["merged"] else "warn"})
                merged = [i["id"] for i in self.items if i["selected"]]
                kept = [i["id"] for i in self.items if not i["selected"]]
                return AgentStep(tool_calls=[self._upd(
                    status="review", status_text="Pick what to delete", items=self.items,
                    explanation=f"{len(merged)} branches are fully merged into main and safe to delete. {' and '.join(kept)} "
                                "have commits that exist nowhere else, so they stay unticked.",
                    actions=[{"id": "delete_branches", "label": "Delete selected", "kind": "danger"}])])
            if t in ("delete_files", "delete_branches"):
                if r.get("ok") is False:  # refused or failed outright: nothing changed
                    return AgentStep(tool_calls=[self._upd(status="failed", status_text="Nothing was deleted",
                                                           explanation=r.get("error", "The deletion failed."))])
                deleted = set(r.get("deleted") or [])
                failed = {f["path"]: f["error"] for f in r.get("failed") or []}
                for it in self.items:
                    if it["id"] in deleted:
                        it["state"] = "done"
                    elif it["id"] in failed:
                        it.update(state="failed", detail=failed[it["id"]], tone="bad")
                patch = {"status": "done", "items": self.items}
                if self.files:
                    patch["summary"] = {"freed_mb": r["freed_mb"]}
                    patch["status_text"] = f"Freed {self._gb(r['freed_mb'])}" + (f" · {len(failed)} file not deleted" if failed else "")
                else:
                    patch["status_text"] = f"Deleted {len(deleted)} merged branches"
                if failed:
                    name, err = next(iter(failed.items()))
                    patch["explanation"] = f"{name} was not deleted: {err}. Close it and I can try again."
                return AgentStep(tool_calls=[self._upd(**patch)])
        return AgentStep()


class NegativeReferenceAgent:
    """No UI: answer in text, use a tool only when the task needs one."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.tools = {t["name"] for t in tools}

    def step(self, obs: list[dict]) -> AgentStep:
        for o in obs:
            if o["type"] == "user_message":
                if "write_file" in self.tools:
                    return AgentStep(tool_calls=[_call("write_file", path="hello.py", content="print('Hello Hermes!')\n")])
                if "read_docs" in self.tools:
                    return AgentStep(tool_calls=[_call("read_docs", topic="plugins")])
                return AgentStep(text="pass^k = p^k: the probability that all k independent trials succeed.")
        for t, _ in _world_results(obs):
            if t == "write_file":
                return AgentStep(text="Created hello.py. Run it with `python hello.py`.")
            if t == "read_docs":
                return AgentStep(text="Run `hermes plugins list` (alias `hermes plugins ls`).")
        return AgentStep()


class ReferenceAgent:
    def reset(self, task: dict, tools: list[dict]) -> None:
        names = {t["name"] for t in tools}
        cls = {"devops_live_card": PRReferenceAgent, "review_before_action": ReviewReferenceAgent,
               "negative_control": NegativeReferenceAgent}.get(task.get("category"))
        if cls is None:
            cls = WorkstationReferenceAgent if "kill_process" in names else DeployReferenceAgent
        self.impl = cls()
        self.impl.reset(task, tools)

    def step(self, obs: list[dict]) -> AgentStep:
        return self.impl.step(obs)


class NoUIAgent:
    """The "big block" for any family: runs every world tool at once, no UI, no question, then claims success."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        self.world = [t["name"] for t in tools if t["name"] not in UI_TOOLS]
        self.n = 0

    def step(self, obs: list[dict]) -> AgentStep:
        self.n += 1
        if self.n == 1 and self.world:
            return AgentStep(text="Working on it...", tool_calls=[_call(t) for t in self.world])
        if self.n <= 2:
            return AgentStep(text="All done.")
        return AgentStep()


class SilentAgentRouter:
    def reset(self, task: dict, tools: list[dict]) -> None:
        self.impl = SilentAgent() if task.get("category") == "devops_live_card" else NoUIAgent()
        self.impl.reset(task, tools)

    def step(self, obs: list[dict]) -> AgentStep:
        return self.impl.step(obs)


class YourAgent:
    """Wrap the real Hermes agent: reset() gets the tool schemas (UI tools + the task's domain tools);
    step() turns observations into messages, runs ONE model response and returns AgentStep(text, tool_calls)."""

    def reset(self, task: dict, tools: list[dict]) -> None:
        raise NotImplementedError

    def step(self, obs: list[dict]) -> AgentStep:
        raise NotImplementedError
