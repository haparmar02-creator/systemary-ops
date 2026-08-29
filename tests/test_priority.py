import unittest

from orchestrator.memory import BusinessState, assess
from orchestrator.priority import Category, WEIGHTS, identify_candidate_actions, prioritize


class RevenueFirstOrderingTest(unittest.TestCase):
    def test_category_weights_are_strictly_descending_in_spec_order(self):
        order = [
            Category.REVENUE, Category.LEADS, Category.GROWTH, Category.QUALITY,
            Category.RETENTION, Category.BRAND, Category.EFFICIENCY,
        ]
        weights = [WEIGHTS[c] for c in order]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_a_single_revenue_row_outranks_a_pile_of_efficiency_work(self):
        # Even with maxed-out urgency on the low-priority side, the
        # category floor for REVENUE must still win: views/likes/pure
        # busywork never outrank the profitable-growth objective.
        efficiency_score = WEIGHTS[Category.EFFICIENCY] + 20  # urgency cap
        revenue_score = WEIGHTS[Category.REVENUE] + 0  # zero urgency
        self.assertGreater(revenue_score, efficiency_score)

    def test_end_to_end_revenue_beats_pipeline_growth_work(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "calendar": [{"id": "c1", "status": "IDEA", "topic": "x"}],
            "revenue": [{"id": "r1", "amount": 5000, "content_attribution": None}],
            "daily_ops_log_today": ["morning-research"],
        })
        assessment = assess(state)
        candidates = identify_candidate_actions(state, assessment)
        tasks = prioritize(candidates)
        self.assertGreaterEqual(len(tasks), 2)
        self.assertEqual(tasks[0].agent, "revenue")


class CandidateGenerationTest(unittest.TestCase):
    def test_empty_state_yields_no_candidates(self):
        state = BusinessState.from_dict({"as_of": "now", "daily_ops_log_today": ["morning-research"]})
        assessment = assess(state)
        self.assertEqual(identify_candidate_actions(state, assessment), [])

    def test_idea_records_trigger_content_strategy(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "calendar": [{"id": "c1", "status": "IDEA", "topic": "x"}],
            "daily_ops_log_today": ["morning-research"],
        })
        assessment = assess(state)
        tasks = prioritize(identify_candidate_actions(state, assessment))
        agents = {t.agent for t in tasks}
        self.assertIn("content_strategy", agents)

    def test_production_without_asset_link_generates_no_qc_candidate(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "calendar": [{"id": "c1", "status": "PRODUCTION", "topic": "x", "asset_link": None}],
            "daily_ops_log_today": ["morning-research"],
        })
        assessment = assess(state)
        tasks = prioritize(identify_candidate_actions(state, assessment))
        self.assertEqual(tasks, [])  # correctly idle: waiting on a human, not on any agent

    def test_production_with_asset_link_triggers_qc(self):
        state = BusinessState.from_dict({
            "as_of": "now",
            "calendar": [{"id": "c1", "status": "PRODUCTION", "topic": "x", "asset_link": "https://x"}],
            "daily_ops_log_today": ["morning-research"],
        })
        assessment = assess(state)
        tasks = prioritize(identify_candidate_actions(state, assessment))
        self.assertEqual([t.agent for t in tasks], ["qc"])


if __name__ == "__main__":
    unittest.main()
