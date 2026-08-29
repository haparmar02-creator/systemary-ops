"""Run a simulated dry-run cycle, or the YouTube publishing dry-run,
from the command line.

    python3 -m orchestrator.cli dry-run
    python3 -m orchestrator.cli dry-run --snapshot fixtures/sample_state.json
    python3 -m orchestrator.cli youtube-dry-run
    python3 -m orchestrator.cli youtube-dry-run --record fixtures/youtube_test_record.json

Neither subcommand makes a real Airtable/Notion/Drive/YouTube call --
nothing published, nothing spent. They exist so a human can watch the
decision loop and the publishing gate work without needing pytest/
unittest installed or a live LLM in the loop.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator.memory import BusinessState
from orchestrator.orchestrator import run_until_idle
from orchestrator.schema import ApprovalRequirement, Task
from orchestrator.simulate import simulate_agent_execution

DEFAULT_SNAPSHOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_state.json"
DEFAULT_YOUTUBE_RECORD = Path(__file__).resolve().parent.parent / "fixtures" / "youtube_test_record.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    dry_run_p = sub.add_parser("dry-run", help="run a simulated cycle chain, no real writes")
    dry_run_p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    dry_run_p.add_argument("--max-cycles", type=int, default=25)
    yt_p = sub.add_parser("youtube-dry-run", help="Priority 3A TEST 1: dry-run publish of one record")
    yt_p.add_argument("--record", type=Path, default=DEFAULT_YOUTUBE_RECORD)
    sub.add_parser("youtube-auth-check", help="Phase 6: verify real OAuth credentials work, no upload")
    args = parser.parse_args(argv)

    if args.command == "dry-run":
        return _dry_run(args.snapshot, args.max_cycles)
    if args.command == "youtube-dry-run":
        return _youtube_dry_run(args.record)
    if args.command == "youtube-auth-check":
        return _youtube_auth_check()
    return 1


def _youtube_auth_check() -> int:
    """Requires YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/YOUTUBE_REFRESH_TOKEN
    in the environment and google-api-python-client installed (see .venv/).
    Never prints a credential value."""
    from orchestrator.publishing.youtube_adapter import MissingCredentialsError, credentials_from_env

    print("=== YOUTUBE AUTH CHECK (no upload) ===")
    try:
        credentials = credentials_from_env()
    except MissingCredentialsError as exc:
        print(f"AUTHENTICATION TEST: FAIL\n  {exc}")
        return 1

    try:
        from orchestrator.publishing.google_client import verify_authentication
    except ImportError as exc:
        print(f"AUTHENTICATION TEST: FAIL\n  google-api-python-client not installed: {exc}")
        return 1

    result = verify_authentication(credentials)
    if result["status"] == "PASS":
        print("AUTHENTICATION TEST: PASS")
        print(f"  channel: {result.get('channel_title')} ({result.get('channel_id')})")
    else:
        print(f"AUTHENTICATION TEST: FAIL\n  {result.get('error')}")
    print("\nNo token value was printed at any point.")
    return 0 if result["status"] == "PASS" else 1


def _youtube_dry_run(record_path: Path) -> int:
    from orchestrator.publishing.idempotency import InMemoryIdempotencyStore
    from orchestrator.publishing.publishing_agent import execute_publish
    from orchestrator.publishing.youtube_adapter import YouTubeAdapter

    record = json.loads(record_path.read_text())
    print(f"=== YOUTUBE DRY RUN (no upload, no credentials touched) -- record: {record_path} ===")
    print(f"1. record read: id={record.get('id')} status={record.get('status')} platform={record.get('platform')}")

    task = Task(
        agent="publishing", objective=f"publish {record.get('id')} to YouTube", inputs={},
        constraints=["dry run only"], expected_output="the exact request that would be sent",
        approval_requirement=ApprovalRequirement.NONE,
    )
    adapter = YouTubeAdapter(idempotency_store=InMemoryIdempotencyStore())  # no real_client_factory at all
    result = execute_publish(record, adapter, task, dry_run=True)

    print(f"\nresult: {result.status.value}")
    for e in result.evidence:
        print(f"  evidence: {e}")
    for e in result.errors:
        print(f"  error: {e}")
    if result.output.get("request_body"):
        print("\nexact request that would be sent to videos.insert:")
        print(json.dumps(result.output["request_body"], indent=2))
    print(f"\nnext: {result.next_recommended_action}")
    print("\nNo network call was made. No credential was read. Nothing was uploaded.")
    return 0 if result.status.value == "succeeded" else 1


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
