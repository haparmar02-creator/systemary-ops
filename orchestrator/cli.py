"""Run a simulated dry-run cycle from the command line.

    python3 -m orchestrator.cli dry-run
    python3 -m orchestrator.cli dry-run --snapshot fixtures/sample_state.json

This uses simulate.py's stubbed agent executor -- no real Airtable/
Notion/Drive calls, nothing published, nothing spent. It exists so a
human can watch the decision loop work without needing pytest/unittest
installed or a live LLM in the loop.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator.memory import BusinessState
from orchestrator.orchestrator import run_until_idle
from orchestrator.simulate import simulate_agent_execution

DEFAULT_SNAPSHOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    dry_run_p = sub.add_parser("dry-run", help="run a simulated cycle chain, no real writes")
    dry_run_p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    dry_run_p.add_argument("--max-cycles", type=int, default=25)
    args = parser.parse_args(argv)

    if args.command == "dry-run":
        return _dry_run(args.snapshot, args.max_cycles)
    return 1


def _dry_run(snapshot_path: Path, max_cycles: int) -> int:
    snapshot = json.loads(snapshot_path.read_text())
    state = BusinessState.from_dict(snapshot)

    print(f"=== DRY RUN (no real writes) -- snapshot: {snapshot_path} ===")
    reports = run_until_idle(state, simulate_agent_execution, dry_run=True, max_cycles=max_cycles)

    for i, report in enumerate(reports, start=1):
        print(f"\n--- cycle {i} ---")
        print(report.summary())
        if report.acted:
            for u in report.result.airtable_updates:
                verb = "CREATE" if u.record_id is None else f"UPDATE {u.record_id}"
                print(f"    intent: {verb} {u.table} <- {u.fields} (applied={u.applied})")
            for e in report.result.evidence:
                print(f"    evidence: {e}")
            if report.result.next_recommended_action:
                print(f"    next: {report.result.next_recommended_action}")
        if report.verification_problems:
            print(f"    VERIFICATION PROBLEMS: {report.verification_problems}")

    print(f"\n=== done: {len(reports)} cycle(s), idle after the last one ===")
    print("No Airtable/Notion/Drive writes were performed -- this ran entirely in-memory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
