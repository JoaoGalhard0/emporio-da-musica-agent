"""Run the eval scenarios against the real model.

    python evals/run_evals.py                      # all scenarios once
    python evals/run_evals.py --only return_regret_flow order_wrong_identity
    python evals/run_evals.py --repeat 3           # LLM output varies: measure the pass rate

Writes transcripts to evals/transcripts/ and a summary to evals/results.md. Exit code is 1 if any
scenario fails. Calls the provider, so it spends free-tier quota; steps are paced on purpose.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from framework import IMPLICIT, Ctx, Observed, Scenario
from scenarios import SCENARIOS

from emporio_agent.agent import Agent, ToolCallTrace
from emporio_agent.cli import Turn, build_agent, to_markdown
from emporio_agent.config import STORE_TZ, store_now
from emporio_agent.session import Session

HERE = Path(__file__).parent
PAUSE_SECONDS = 1.5  # keeps a long run inside the free-tier request limits


@dataclass
class Outcome:
    scenario: Scenario
    passed: bool
    failures: list[str]  # "step N: <check>"
    turns: list[Turn]


def run_scenario(agent: Agent, scenario: Scenario, ctx: Ctx) -> Outcome:
    os.environ["STORE_NOW"] = scenario.now
    session, turns, calls_so_far, failures = Session(), [], [], []
    for number, step in enumerate(scenario.steps, start=1):
        text = step.text(ctx)
        result = agent.reply(session, text)
        turns.append(Turn(text, result))
        calls_so_far.extend(result.tool_calls)
        obs = Observed(text, result, session, list(calls_so_far))
        for check in [*IMPLICIT, *step.checks]:
            problem = check.run(obs)
            if problem:
                failures.append(f"step {number}: {problem}")
        time.sleep(PAUSE_SECONDS)
    return Outcome(scenario, not failures, failures, turns)


def run_with_retry(agent: Agent, scenario: Scenario, ctx: Ctx) -> Outcome:
    """A provider hiccup (quota, 5xx) is not the agent's fault: retry the scenario once."""
    outcome = run_scenario(agent, scenario, ctx)
    if any(t.result.failed for t in outcome.turns):
        time.sleep(20)
        outcome = run_scenario(agent, scenario, ctx)
    return outcome


def write_report(directory: Path, model: str, outcomes: dict[str, list[Outcome]], fresh: bool) -> None:
    """Merge this invocation into evals/results.json and render evals/results.md.

    The full suite is run in several batches (one process each) to keep memory low, so the report
    accumulates per scenario instead of being overwritten; `--fresh` starts it over.
    """
    json_path = directory / "results.json"
    stored: dict = {}
    if json_path.exists() and not fresh:
        stored = json.loads(json_path.read_text(encoding="utf-8"))
    for name, runs in outcomes.items():
        stored[name] = {
            "runs": len(runs),
            "passed": sum(o.passed for o in runs),
            "failures": sorted({f for o in runs for f in o.failures}),
            "model": model,
            "when": f"{datetime.now(STORE_TZ):%d/%m/%Y %H:%M}",
        }
    json_path.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")

    order = [s.name for s in SCENARIOS if s.name in stored]
    runs_total = sum(stored[n]["runs"] for n in order)
    runs_passed = sum(stored[n]["passed"] for n in order)
    all_pass = sum(stored[n]["passed"] == stored[n]["runs"] for n in order)
    lines = [
        "# Eval results", "",
        f"Model `{model}` · {len(order)}/{len(SCENARIOS)} scenarios run · "
        f"**{runs_passed}/{runs_total} runs passed** · {all_pass}/{len(order)} scenarios passed every run", "",
        "| Scenario | Passed runs | Last run | What failed |", "|---|---|---|---|",
    ]
    for name in order:
        r = stored[name]
        failed = "; ".join(r["failures"]) if r["failures"] else "—"
        lines.append(f"| `{name}` | {r['passed']}/{r['runs']} | {r['when']} | {failed} |")
    (directory / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="scenario names to run")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--fresh", action="store_true", help="discard previously stored results")
    args = parser.parse_args()
    for stream in (sys.stdout,):
        stream.reconfigure(encoding="utf-8")

    chosen = [s for s in SCENARIOS if not args.only or s.name in args.only]
    unknown = set(args.only or []) - {s.name for s in SCENARIOS}
    if unknown:
        print(f"Unknown scenarios: {sorted(unknown)}")
        return 2

    agent = build_agent()
    agent.escalations_path = Path(tempfile.mkdtemp()) / "escalations.jsonl"  # keep real tickets clean
    ctx = Ctx(agent.store)
    (HERE / "transcripts").mkdir(exist_ok=True)

    outcomes: dict[str, list[Outcome]] = {}
    for scenario in chosen:
        runs = []
        for attempt in range(args.repeat):
            outcome = run_with_retry(agent, scenario, ctx)
            runs.append(outcome)
            mark = "PASS" if outcome.passed else "FAIL"
            print(f"[{mark}] {scenario.name}" + (f" (run {attempt + 1})" if args.repeat > 1 else ""), flush=True)
            for failure in outcome.failures:
                print(f"       - {failure}")
            if not outcome.passed:
                for turn in outcome.turns:
                    print(f"       customer: {turn.user}\n       agent: {turn.result.text[:300]!r}")
        outcomes[scenario.name] = runs
        last = runs[-1]
        os.environ["STORE_NOW"] = scenario.now
        md = to_markdown(scenario.title, last.turns, store_now(), agent.llm.model)
        (HERE / "transcripts" / f"{scenario.name}.md").write_text(md, encoding="utf-8")
        if scenario.example and last.passed:
            # Only a run that passed every check is published, and it is the real, unedited output.
            examples = HERE.parent / "examples"
            examples.mkdir(exist_ok=True)
            (examples / f"{scenario.example}.md").write_text(md, encoding="utf-8")

    write_report(HERE, agent.llm.model, outcomes, args.fresh)
    failed = [n for n, v in outcomes.items() if not all(o.passed for o in v)]
    print(f"\n{len(outcomes) - len(failed)}/{len(outcomes)} scenarios fully passing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
