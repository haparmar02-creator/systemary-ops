import unittest

from orchestrator.schema import (
    AirtableUpdateIntent,
    ApprovalRequirement,
    Result,
    Task,
    TaskStatus,
)


class TaskResultSchemaTest(unittest.TestCase):
    def test_task_has_stable_id_and_serializes(self):
        t = Task(
            agent="research",
            objective="do a thing",
            inputs={"x": 1},
            constraints=["no fabrication"],
            expected_output="a list of opportunities",
            approval_requirement=ApprovalRequirement.NONE,
        )
        self.assertTrue(t.task_id.startswith("task_"))
        d = t.to_dict()
        self.assertEqual(d["approval_requirement"], "none")
        self.assertEqual(d["agent"], "research")

    def test_two_tasks_get_distinct_ids(self):
        make = lambda: Task(
            agent="research", objective="x", inputs={}, constraints=[],
            expected_output="y", approval_requirement=ApprovalRequirement.NONE,
        )
        self.assertNotEqual(make().task_id, make().task_id)

    def test_result_ok_property(self):
        r = Result(
            task_id="task_1", agent="research", status=TaskStatus.SUCCEEDED,
            output={}, evidence=[], errors=[], airtable_updates=[],
            next_recommended_action=None,
        )
        self.assertTrue(r.ok)
        r2 = Result(**{**r.__dict__, "status": TaskStatus.FAILED})
        self.assertFalse(r2.ok)

    def test_airtable_update_intent_defaults_unapplied(self):
        u = AirtableUpdateIntent(table="Calendar", record_id="rec1", fields={"Status": "SCRIPT"})
        self.assertFalse(u.applied)


if __name__ == "__main__":
    unittest.main()
