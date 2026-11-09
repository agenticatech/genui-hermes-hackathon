"""Run the GenUI v3 benchmark.

  python run_eval.py --agent reference
  python run_eval.py --agent silent
  python run_eval.py --agent mypkg.hermes_adapter:HermesAgent --theme acme --screens
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from genui3.agents import ReferenceAgent, SilentAgentRouter
from genui3.grader import grade
from genui3.runner import THEMES, run_task
from genui3.sim import ScriptedUser

HERE = Path(__file__).resolve().parent
AGENTS = {"reference": ReferenceAgent, "silent": SilentAgentRouter}


def load_agent(spec: str):
    if spec in AGENTS:
        return AGENTS[spec]()
    mod, cls = spec.split(":")
    return getattr(importlib.import_module(mod), cls)()


def main() -> None:
    # Check details print arrows; a Windows console defaults to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(HERE / "tasks_v3.jsonl"))
    ap.add_argument("--agent", default="reference")
    ap.add_argument("--theme", default="default", help="themes/<name>/<component>.js, falls back to default")
    ap.add_argument("--themes", default=str(THEMES), help="folder holding <theme>/<component>.js (default: the plugin's)")
    ap.add_argument("--task", nargs="*", help="only these task_ids")
    ap.add_argument("--screens", action="store_true", help="save one screenshot per UI change")
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()

    out = Path(args.out)
    (out / "traces").mkdir(parents=True, exist_ok=True)
    tasks = [json.loads(l) for l in open(args.tasks, encoding="utf-8") if l.strip()]
    if args.task:
        tasks = [t for t in tasks if t["task_id"] in args.task]
    rows = []
    for task in tasks:
        trace = run_task(task, load_agent(args.agent), ScriptedUser(task), theme=args.theme,
                         screenshots=out / "screens" / task["task_id"] if args.screens else None,
                         themes_dir=Path(args.themes))
        res = grade(task, trace)
        rows.append(res)
        (out / "traces" / f"{task['task_id']}.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{'PASS' if res['passed'] else 'FAIL'}  {task['task_id']:<20} score={res['score']:.2f}")
        for c in res["checks"]:
            print(f"   {c['status']:<4} {c['check']:<34} {c['detail']}")
    (out / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\npass rate {sum(r['passed'] for r in rows) / len(rows):.0%}")


if __name__ == "__main__":
    main()
