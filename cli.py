"""Command-line entry point.

    python cli.py run "Find 10 dentists in Pune" [--max-steps N]
    python cli.py learn
    python cli.py label <run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from prospector.agent import Agent, RunState, Step
from prospector.learner import learn
from prospector.llm import GeminiLLM, LLMError
from prospector.memory import Memory


def _on_step(step: Step, _state) -> None:
    status = "ok" if step.ok else "FAIL"
    print(f"[{step.n:02d}] ({status}) {step.action}({step.args}) -> {step.observation}")


def cmd_run(args: argparse.Namespace) -> int:
    try:
        llm = GeminiLLM()
    except LLMError as exc:
        print(f"Cannot run: {exc}", file=sys.stderr)
        return 1

    memory = Memory(Path("data"))
    agent = Agent(llm, memory, max_steps=args.max_steps, runs_dir=Path("runs"), on_step=_on_step)
    state = agent.run(args.goal)

    print(f"\nRun {state.run_id} finished with status={state.status}")
    print(f"Leads found: {len(state.leads)}")
    print(f"Report: runs/{state.run_id}/report.md")
    print(f"CSV:    runs/{state.run_id}/leads.csv")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    try:
        llm = GeminiLLM()
    except LLMError as exc:
        print(f"Cannot learn: {exc}", file=sys.stderr)
        return 1

    memory = Memory(Path("data"))
    report = learn(memory, llm)
    print(report.message)
    if report.ok:
        print(f"Test accuracy: {report.acc_before:.1f}% -> {report.acc_after:.1f}%")
        p_before = "n/a" if report.p_at_10_before is None else f"{report.p_at_10_before:.1f}%"
        p_after = "n/a" if report.p_at_10_after is None else f"{report.p_at_10_after:.1f}%"
        print(f"p@k: {p_before} -> {p_after}")
        print(f"Added: {[r.id for r in report.added]}")
        print(f"Removed: {[r.id for r in report.removed]}")
    return 0


def cmd_label(args: argparse.Namespace) -> int:
    state_path = Path("runs") / args.run_id / "state.json"
    if not state_path.exists():
        print(f"No state.json found at {state_path}", file=sys.stderr)
        return 1

    state = RunState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
    memory = Memory(Path("data"))
    leads = sorted(state.leads.values(), key=lambda ld: ld.score, reverse=True)

    print(f"Labeling {len(leads)} leads from {args.run_id}. Enter g=good, b=bad, s=skip, q=quit.")
    for lead in leads:
        answer = input(f"{lead.name} ({lead.niche}, score={lead.score:.0f}) [g/b/s/q]: ").strip().lower()
        if answer == "q":
            break
        if answer not in ("g", "b"):
            continue
        memory.add_label(lead, "good" if answer == "g" else "bad", args.run_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="prospector")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the agent on a goal")
    p_run.add_argument("goal")
    p_run.add_argument("--max-steps", type=int, default=25)
    p_run.set_defaults(func=cmd_run)

    p_learn = sub.add_parser("learn", help="Run the learning loop over collected labels")
    p_learn.set_defaults(func=cmd_learn)

    p_label = sub.add_parser("label", help="Label leads from a past run good/bad")
    p_label.add_argument("run_id")
    p_label.set_defaults(func=cmd_label)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
