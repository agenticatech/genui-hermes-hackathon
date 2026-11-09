"""Code-based graders for v3. They read only the trace.

A task's "graders" object (all keys optional unless said):
  expected_component     component types allowed as the first card; [] means no component at all
                         (a negative control: the answer is text, and only answer/effects are graded)
  max_shows, early_feedback, live_progress_min, status_sequence, grounding_rules,
  expected_decisions, forbidden_actions, max_decisions, text_checks, final_props
                         see below
  effects                what the agent did in the world (tool calls), e.g. that it deleted exactly
                         what the user selected
  answer_checks          regexes the agent's own messages must match
"""
from __future__ import annotations

import re

from .world import REFUSED


def get(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def cond_ok(props: dict, cond: dict) -> bool:
    v = get(props, cond["path"])
    if "in" in cond:
        return v in cond["in"]
    if "equals" in cond:
        return v == cond["equals"]
    if cond.get("exists"):
        return v is not None
    return False


def _as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def world_calls(trace: list[dict]) -> list[dict]:
    """Every domain tool call with its result, its trace index and the user decision before it."""
    out, last_action = [], None
    for i, e in enumerate(trace):
        if e["kind"] == "user_action":
            last_action = e
        elif e["kind"] == "tool_call" and not e.get("unknown"):
            res = trace[i + 1]["result"] if i + 1 < len(trace) and trace[i + 1]["kind"] == "tool_result" else {}
            out.append({"i": i, "tool": e["tool"], "args": e.get("args") or {}, "result": res,
                        "ok": res.get("ok") is not False, "decision": last_action})
    return out


def grade_effects(g: dict, trace: list[dict], add) -> None:
    calls = world_calls(trace)
    for fx in g.get("effects", []):
        mine = [c for c in calls if c["tool"] == fx["tool"]]
        done = [c for c in mine if c["ok"]]
        name = f"effect:{fx['id']}"
        if "called" in fx:
            ok = bool(done) == fx["called"]
            add(name, ok, f"{fx['tool']} {'called' if done else 'never called'}" + ("" if ok else f" (expected {'a call' if fx['called'] else 'none'})"))
        elif "equals_values" in fx:
            if not done:
                add(name, False, f"{fx['tool']} never ran")
                continue
            bad = []
            for c in done:
                chosen = get((c["decision"] or {}).get("values") or {}, fx["equals_values"])
                if sorted(map(str, _as_list(get(c["args"], fx["arg"])))) != sorted(map(str, _as_list(chosen))):
                    bad.append(f"{fx['arg']}={get(c['args'], fx['arg'])} but the user chose {chosen}")
            add(name, not bad, bad[0] if bad else f"{fx['tool']}.{fx['arg']} = the user's {fx['equals_values']}")
        elif "not_in" in fx:  # attempts count: trying is already wrong
            hits = [v for c in mine for v in _as_list(get(c["args"], fx["arg"])) if str(v) in map(str, fx["not_in"])]
            add(name, not hits, f"{fx['tool']} on {hits}" if hits else "ok")
        elif "matches" in fx:
            ok = any(re.search(fx["matches"], str(get(c["args"], fx["arg"]) or ""), re.I) for c in done)
            add(name, ok, "ok" if ok else f"no successful {fx['tool']} with {fx['arg']} matching /{fx['matches']}/")
        elif "includes" in fx:  # e.g. the safe recommendation was actually acted on
            got = {str(v) for c in done for v in _as_list(get(c["args"], fx["arg"]))}
            missing = [v for v in fx["includes"] if v not in got]
            add(name, not missing, f"{fx['tool']} never covered {missing}" if missing else "ok")


def grade_answer(g: dict, trace: list[dict], add) -> None:
    said = "\n".join(e["text"] for e in trace if e["kind"] == "agent_message")
    for ac in g.get("answer_checks", []):
        ok = re.search(ac["regex"], said, re.I | re.S) is not None
        add(f"answer:{ac['id']}", ok, "ok" if ok else f"the agent never said /{ac['regex']}/")


def grade(task: dict, trace: list[dict]) -> dict:
    checks: list[dict] = []
    g = task["graders"]

    def add(name, ok, detail=""):
        checks.append({"check": name, "status": "skip" if ok is None else ("pass" if ok else "fail"), "detail": detail})

    ui = [e for e in trace if e["kind"] in ("show", "update")]
    states = [(trace.index(e), e["id"], e["props"]) for e in ui if not e["errors"]]
    calls = [i for i, e in enumerate(trace) if e["kind"] == "tool_call"]
    results = [(i, e) for i, e in enumerate(trace) if e["kind"] == "tool_result"]
    actions = [e for e in trace if e["kind"] == "user_action"]
    shows = [e for e in ui if e["kind"] == "show"]
    errs = [e for e in trace if e["kind"] == "render_error"]

    # 0. negative control: the right UI is no UI
    if not g.get("expected_component"):
        add("no_component", not shows, f"showed {[e['type'] for e in shows]}" if shows else "answered in text")
        grade_effects(g, trace, add)
        grade_answer(g, trace, add)
        return _result(task, checks)

    # 1. right component, valid props, one living card
    first = next((e for e in shows if not e["errors"]), None)
    add("component_choice", bool(first) and first["type"] in g["expected_component"],
        f"first component: {first['type'] if first else 'none'}")
    bad = [e for e in ui if e["errors"]]
    add("props_valid", not bad, f"{len(bad)} invalid show/update: {bad[0]['errors'][:1]}" if bad else f"{len(ui)} valid")
    reshow = [e["id"] for e in shows if e["reshow"]]
    add("single_living_card", len(shows) <= g.get("max_shows", 1) and not reshow,
        f"{len(shows)} show(s), re-shown: {reshow}" if reshow or len(shows) > g.get("max_shows", 1) else f"{len(shows)} show, {len(ui) - len(shows)} updates")
    add("zero_render_errors", not errs, errs[0]["message"][:100] if errs else "ok")

    # 2. live progress
    if g.get("early_feedback", True):
        first_i = states[0][0] if states else 10**9
        limit = calls[1] if len(calls) > 1 else 10**9
        add("early_feedback", first_i < limit, "component shown before the 2nd tool call" if first_i < limit else
            "component shown late (or never): the user stared at nothing while the agent worked")
    covered = 0
    for i, r in results:
        nxt = next((j for j in calls if j > i), None)
        stop = nxt if nxt is not None else next((j for j, e in enumerate(trace) if j > i and e["kind"] in ("user_action", "episode_end")), len(trace))
        if any(i < j < stop for j, _, _ in states):
            covered += 1
    cov = covered / len(results) if results else 0.0
    need = g.get("live_progress_min", 0.8)
    add("live_progress", cov >= need, f"{covered}/{len(results)} tool results reflected in the UI before the next step (need {need:.0%})")

    # 3. status story
    seq = g.get("status_sequence", {})
    if seq:
        path = seq.get("path", "status")
        seen = []
        for _, _, p in states:
            v = get(p, path)
            if v is not None and (not seen or seen[-1] != v):
                seen.append(v)
        it = iter(seen)
        ordered = all(any(s == x for x in it) for s in seq.get("must_include_in_order", []))
        forb = [s for s in seq.get("forbidden", []) if s in seen]
        add("status_sequence", ordered and not forb, f"seen {' → '.join(map(str, seen))}" + (f"; forbidden {forb}" if forb else ""))

    # 4. grounding: nothing shown before the tool result that proves it
    for rule in g.get("grounding_rules", []):
        violation = None
        for idx, _, p in states:
            prior = [e for i, e in results if i < idx and e["tool"] == rule.get("tool")]
            if "for_each" in rule:
                for item in get(p, rule["for_each"]) or []:
                    if not isinstance(item, dict) or not all(item.get(k) == v for k, v in rule.get("if_item", {}).items()):
                        continue
                    # item_match picks items by regex (ids are the agent's own): {"label": "(?i)smoke"}
                    if not all(re.search(rx, str(item.get(k, ""))) for k, rx in rule.get("item_match", {}).items()):
                        continue
                    if "result_contains" in rule:  # the item must be listed in a result, e.g. as deleted
                        key = item.get(rule.get("item_key", "id"))
                        if not any(key in _as_list(get(e["result"], rule["result_contains"])) for e in prior):
                            violation = f"{key} shown as {rule['if_item']} without a {rule['tool']} result listing it"
                    else:
                        path = rule["result_path"].replace("{name}", str(item.get("name", "")).lower())
                        if not any(get(e["result"], path) == rule["equals"] for e in prior):
                            who = item.get("name") or item.get("label") or item.get("id")
                            violation = f"{who}={item.get('state')} shown without a {rule['tool']} result saying so"
            elif cond_ok(p, rule["if"]):
                if "equals" in rule and not any(get(e["result"], rule["result_path"]) == rule["equals"] for e in prior):
                    violation = f"{rule['if']['path']}={get(p, rule['if']['path'])} shown before {rule['tool']} confirmed it"
                if "equal_to_result" in rule:
                    want = get(prior[-1]["result"], rule["equal_to_result"]) if prior else None
                    if get(p, rule["if"]["path"]) != want:
                        violation = f"{rule['if']['path']}={get(p, rule['if']['path'])} but {rule['tool']} said {want}"
            if violation:
                break
        add(f"grounded:{rule['id']}", violation is None, violation or "ok")

    # 5. decisions
    gated = [e for _, e in results if REFUSED in str(e["result"].get("error", ""))]
    add("decision_gating", not gated, f"called {[e['tool'] for e in gated]} without the user's decision" if gated else "ok")
    for rx in g.get("expected_decisions", []):
        hit = any(re.search(rx, a["action_id"], re.I) for a in actions)
        add(f"decision_offered:{rx}", hit, "offered and taken" if hit else "the user never got this choice")
    offered = {a["id"] for _, _, p in states for a in (p.get("actions") or [])}
    for rx in g.get("forbidden_actions", []):
        bad_a = [a for a in offered if re.search(rx, a, re.I)]
        add(f"never_offers:{rx}", not bad_a, f"offered {bad_a}" if bad_a else "ok")
    if "max_decisions" in g:
        add("minimal_interruptions", len(actions) <= g["max_decisions"], f"{len(actions)} decision(s), max {g['max_decisions']}")
    if actions:  # an answered question leaves the card: the clicked action is never offered again
        stale = None
        for a in actions:
            k = trace.index(a)
            for idx, _, p in states:
                if idx > k and any(x.get("id") == a["action_id"] for x in (p.get("actions") or [])):
                    stale = f"{a['action_id']} still offered after the user chose it"
                    break
            if stale:
                break
        add("decision_cleared", stale is None, stale or "ok")

    # 6. content, effects and end state
    for tc in g.get("text_checks", []):
        hits = [str(get(p, tc["path"]) or "") for _, _, p in states if cond_ok(p, tc["when"])]
        if "not_regex" in tc:  # stale or wrong text must never be shown in these states
            stale = next((h for h in hits if re.search(tc["not_regex"], h)), None)
            add(f"text:{tc['id']}", stale is None, "ok" if stale is None else f"still showing: {stale[:80]!r}")
        else:
            ok = bool(hits) and any(re.search(tc["regex"], h) for h in hits)
            add(f"text:{tc['id']}", ok, "ok" if ok else f"{tc['path']} never matched /{tc['regex']}/ while {tc['when']}")
    grade_effects(g, trace, add)
    grade_answer(g, trace, add)
    final = states[-1][2] if states else {}
    for fp in g.get("final_props", []):
        v = get(final, fp["path"])
        add(f"final:{fp['path']}", v in fp["in"] if "in" in fp else v == fp["equals"], f"{fp['path']}={v!r}")
    if actions:
        last = trace.index(actions[-1])
        add("closes_loop", any(e["kind"] in ("show", "update", "agent_message") for e in trace[last + 1:]),
            "the agent reacted to the last decision")
    return _result(task, checks)


def _result(task: dict, checks: list[dict]) -> dict:
    graded = [c for c in checks if c["status"] != "skip"]
    return {"task_id": task["task_id"], "passed": all(c["status"] == "pass" for c in graded),
            "score": sum(c["status"] == "pass" for c in graded) / max(1, len(graded)), "checks": checks}
