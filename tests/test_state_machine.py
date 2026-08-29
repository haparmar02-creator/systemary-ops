import unittest

from orchestrator.state_machine import (
    CONTENT_STATES,
    IllegalTransition,
    is_forward,
    is_legal,
    known_states,
    validate_transition,
)


class ContentStateMachineTest(unittest.TestCase):
    def test_full_pipeline_is_legal_step_by_step(self):
        for a, b in zip(CONTENT_STATES, CONTENT_STATES[1:]):
            with self.subTest(f"{a} -> {b}"):
                validate_transition("content", a, b)  # must not raise

    def test_skipping_a_stage_is_illegal(self):
        with self.assertRaises(IllegalTransition):
            validate_transition("content", "IDEA", "SCRIPT")

    def test_going_backwards_past_the_allowed_rework_edge_is_illegal(self):
        with self.assertRaises(IllegalTransition):
            validate_transition("content", "PUBLISHED", "IDEA")

    def test_qc_rework_edges_are_legal(self):
        validate_transition("content", "REVIEW", "PRODUCTION")
        validate_transition("content", "AWAITING_APPROVAL", "PRODUCTION")

    def test_same_state_is_a_noop_not_an_error(self):
        validate_transition("content", "SCRIPT", "SCRIPT")

    def test_repurposed_is_terminal(self):
        self.assertEqual(known_states("content")[-1], "REPURPOSED")
        self.assertFalse(is_legal("content", "REPURPOSED", "IDEA"))

    def test_is_forward_on_linear_pipeline(self):
        self.assertTrue(is_forward("content", "IDEA", "SCRIPT"))
        self.assertFalse(is_forward("content", "SCRIPT", "IDEA"))

    def test_awaiting_approval_is_a_single_joined_state(self):
        # Regression guard for the live Airtable bug where this got split
        # into two separate choices ("AWAITING", "APPROVAL"). The state
        # machine must never treat those as valid states.
        self.assertIn("AWAITING_APPROVAL", CONTENT_STATES)
        self.assertNotIn("AWAITING", CONTENT_STATES)
        self.assertNotIn("APPROVAL", CONTENT_STATES)


class LeadStateMachineTest(unittest.TestCase):
    def test_lead_can_be_lost_from_any_non_terminal_stage(self):
        validate_transition("lead", "LEAD", "LOST")
        validate_transition("lead", "CONTACTED", "LOST")
        validate_transition("lead", "PROPOSAL", "LOST")

    def test_won_and_lost_are_terminal(self):
        self.assertEqual(known_states("lead"), ["LEAD", "CONTACTED", "PROPOSAL", "WON", "LOST"])
        self.assertFalse(is_legal("lead", "WON", "LOST"))
        self.assertFalse(is_legal("lead", "LOST", "LEAD"))

    def test_cannot_skip_straight_to_proposal(self):
        with self.assertRaises(IllegalTransition):
            validate_transition("lead", "LEAD", "PROPOSAL")


class ApprovalStateMachineTest(unittest.TestCase):
    def test_pending_resolves_either_way(self):
        validate_transition("approval", "PENDING", "APPROVED")
        validate_transition("approval", "PENDING", "REJECTED")

    def test_resolved_approvals_are_terminal(self):
        self.assertFalse(is_legal("approval", "APPROVED", "REJECTED"))
        self.assertFalse(is_legal("approval", "REJECTED", "PENDING"))


class ExperimentStateMachineTest(unittest.TestCase):
    def test_linear_progression(self):
        validate_transition("experiment", "PLANNED", "RUNNING")
        validate_transition("experiment", "RUNNING", "COMPLETE")

    def test_cannot_skip_running(self):
        with self.assertRaises(IllegalTransition):
            validate_transition("experiment", "PLANNED", "COMPLETE")


if __name__ == "__main__":
    unittest.main()
