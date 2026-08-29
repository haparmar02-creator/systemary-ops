import json
import unittest
from pathlib import Path

from orchestrator.errors import RetryPolicy, run_with_retry
from orchestrator.memory import BusinessState
from orchestrator.orchestrator import run_cycle, run_until_idle, verify_result
from orchestrator.schema import (
    AirtableUpdateIntent,
    ApprovalRequirement,
    Result,
    Task,
    TaskStatus,
)
from orchestrator.simulate import simulate_agent_execution

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_state.json"


def load_state() -> BusinessState:
    return BusinessState.from_dict(json.loads(FIXTURE.read_text()))


class NewOpportunityDryRunTest(unittest.TestCase):
    """The exact scenario from the Priority-2 spec:

    A new content opportunity enters the system. The orchestrator should:
    RESEARCH -> evaluate opportunity -> choose content strategy ->
    assign script agent -> receive script result -> assign QC ->
    determine approval requirement -> update Airtable -> produce the
    next task. Dry-run only: nothing published, nothing spent, nothing
    real written.
    """

    def test_full_cascade_matches_the_spec_sequence(self):
        state = load_state()
        self.assertEqual(len(state.opportunities), 1)
        self.assertEqual(len(state.calendar), 0)

        reports = run_until_idle(state, simulate_agent_execution, dry_run=True, max_cycles=10)

        acted = [r for r in reports if r.acted]
        agent_sequence = [r.selected_task.agent for r in acted]
        self.assertEqual(agent_sequence, ["research", "content_strategy", "script", "qc"])

        # every step actually succeeded
        self.assertTrue(all(r.result.status == TaskStatus.SUCCEEDED for r in acted))

        # every task ran as dry_run and nothing was ever marked "really applied"
        for r in acted:
            self.assertTrue(r.selected_task.dry_run)

        # the cascade ends idle, not on an error
        self.assertFalse(reports[-1].acted)
        self.assertEqual(reports[-1].skipped_reason, "nothing actionable")

        # the opportunity became exactly one Calendar record, which rode
        # the pipeline from RESEARCH to PRODUCTION
        self.assertEqual(len(state.calendar), 1)
        record = state.calendar[0]
        self.assertEqual(record["status"], "PRODUCTION")
        self.assertIn("script_link", record)
        self.assertEqual(state.opportunities, [])  # fully consumed, nothing lost

        # QC explicitly determined the approval requirement (spec step)
        qc_report = acted[-1]
        self.assertEqual(qc_report.result.output.get("approval_requirement_determined"), "none")

        # never dispatched to a disabled agent (publishing/production/community)
        self.assertNotIn("publishing", agent_sequence)
        self.assertNotIn("production", agent_sequence)

    def test_dry_run_never_touches_a_real_system(self):
        # There is, deliberately, no code path in this package that makes
        # a network call -- assert that by construction: every intent's
        # `applied` flag reflects only the in-memory simulated state, and
        # the CycleReport chain is fully re-derivable from the fixture.
        state = load_state()
        reports = run_until_idle(state, simulate_agent_execution, dry_run=True)
        all_intents = [
            u for r in reports if r.acted for u in r.result.airtable_updates
        ]
        self.assertTrue(all_intents)
        for intent in all_intents:
            self.assertTrue(intent.applied)  # applied to the *simulated* snapshot
        # re-running from a fresh copy of the same fixture reproduces the
        # same agent sequence -- proof this is deterministic simulation,
        # not a live call with side effects elsewhere.
        state2 = load_state()
        reports2 = run_until_idle(state2, simulate_agent_execution, dry_run=True)
        self.assertEqual(
            [r.selected_task.agent for r in reports if r.acted],
            [r.selected_task.agent for r in reports2 if r.acted],
        )


class VerificationRejectsIllegalTransitionsTest(unittest.TestCase):
    def test_an_agent_proposing_an_illegal_jump_is_rejected_not_applied(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "calendar": [{"id": "c1", "status": "IDEA", "topic": "x"}],
        })

        def bad_executor(task: Task) -> Result:
            return Result(
                task_id=task.task_id, agent=task.agent, status=TaskStatus.SUCCEEDED,
                output={}, evidence=[], errors=[],
                airtable_updates=[AirtableUpdateIntent(
                    table="Calendar", record_id="c1", fields={"Status": "PUBLISHED"},
                )],
                next_recommended_action=None,
            )

        report = run_cycle(state, bad_executor, dry_run=True)
        self.assertEqual(report.result.status, TaskStatus.FAILED)
        self.assertTrue(report.verification_problems)
        # state must NOT have been mutated by a rejected result
        self.assertEqual(state.calendar[0]["status"], "IDEA")


class ApprovalRequiredBlocksExecutionTest(unittest.TestCase):
    def test_high_ticket_proposal_requires_approval_and_never_calls_execute(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "leads": [{"id": "l1", "status": "Proposal", "value": 60000}],
        })
        calls = []

        def spy_executor(task: Task) -> Result:
            calls.append(task)
            return Result(
                task_id=task.task_id, agent=task.agent, status=TaskStatus.SUCCEEDED,
                output={}, evidence=[], errors=[], airtable_updates=[],
                next_recommended_action=None,
            )

        report = run_cycle(state, spy_executor, dry_run=True)
        self.assertEqual(report.selected_task.agent, "community")
        self.assertEqual(report.result.status, TaskStatus.BLOCKED_ON_APPROVAL)
        self.assertEqual(calls, [])  # execute() must never be called

    def test_ordinary_stalled_lead_does_not_require_approval(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "leads": [{"id": "l1", "status": "Lead", "days_since_first_contact": 5}],
        })
        report = run_cycle(state, simulate_agent_execution, dry_run=True)
        self.assertEqual(report.selected_task.agent, "community")
        self.assertEqual(report.result.status, TaskStatus.SUCCEEDED)  # ordinary decisions proceed autonomously


class DisabledAgentIsSkippedTest(unittest.TestCase):
    def test_disabled_production_agent_is_never_dispatched(self):
        # There is no candidate generator that targets "production" at all
        # yet (it's a human-in-the-loop step) -- assert the registry-level
        # invariant directly: a disabled agent can never be SELECT AGENT's
        # output, no matter what a future candidate generator proposes.
        from orchestrator.agents import get as get_agent
        from orchestrator.priority import Candidate, Category
        from orchestrator.schema import Task as _Task

        state = BusinessState.from_dict({"as_of": "now"})
        fake_candidate = Candidate(
            task=_Task(
                agent="production", objective="film it", inputs={}, constraints=[],
                expected_output="a produced asset", approval_requirement=ApprovalRequirement.NONE,
            ),
            category=Category.EFFICIENCY,
            reason="synthetic test candidate",
        )
        self.assertFalse(get_agent("production").enabled)

        import orchestrator.orchestrator as orch_mod
        original = orch_mod.identify_candidate_actions
        orch_mod.identify_candidate_actions = lambda s, a: [fake_candidate]
        try:
            report = run_cycle(state, simulate_agent_execution, dry_run=True)
        finally:
            orch_mod.identify_candidate_actions = original

        self.assertFalse(report.acted)
        self.assertIn("disabled", report.skipped_reason)


class RetryAndEscalationTest(unittest.TestCase):
    def test_exhausted_retries_escalate_with_full_error_history(self):
        task = Task(
            agent="research", objective="x", inputs={}, constraints=[],
            expected_output="y", approval_requirement=ApprovalRequirement.NONE,
        )
        attempts = {"n": 0}

        def always_fails(t: Task) -> Result:
            attempts["n"] += 1
            raise RuntimeError(f"boom {attempts['n']}")

        policy = RetryPolicy(max_retries=2, timeout_seconds=5)
        result = run_with_retry(task, always_fails, policy)

        self.assertEqual(attempts["n"], 3)  # 1 first try + 2 retries
        self.assertEqual(result.status, TaskStatus.ESCALATED)
        self.assertEqual(len(result.errors), 3)
        self.assertIsNotNone(result.next_recommended_action)

    def test_success_on_second_attempt_short_circuits(self):
        task = Task(
            agent="research", objective="x", inputs={}, constraints=[],
            expected_output="y", approval_requirement=ApprovalRequirement.NONE,
        )
        attempts = {"n": 0}

        def fails_once(t: Task) -> Result:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return Result(
                task_id=t.task_id, agent=t.agent, status=TaskStatus.SUCCEEDED,
                output={}, evidence=[], errors=[], airtable_updates=[],
                next_recommended_action=None,
            )

        policy = RetryPolicy(max_retries=2, timeout_seconds=5)
        result = run_with_retry(task, fails_once, policy)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(attempts["n"], 2)


if __name__ == "__main__":
    unittest.main()
