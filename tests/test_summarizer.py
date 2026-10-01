"""Unit tests for Resume Context Summarizer (V2)."""
import unittest
from breadcrumb.demo_data import get_demo_events
from breadcrumb.aggregator import TimelineAggregator
from breadcrumb.summarizer import RuleBasedSummarizer, ContextSummarizer

class TestSummarizer(unittest.TestCase):
    def test_v2_multi_session_resume_context(self):
        """Verifies V2 multi-session scenario: Session 2 is analyzed with observed vs inferred."""
        demo_raw = get_demo_events()
        sessions = TimelineAggregator.group_into_sessions(demo_raw)
        self.assertEqual(len(sessions), 2)

        latest_session = sessions[-1]
        self.assertEqual(latest_session.session_id, 2)
        self.assertIn("21:20", latest_session.time_span_label)
        self.assertEqual(latest_session.last_event["start_time_label"], "21:49")

        ctx = RuleBasedSummarizer.summarize(latest_session.events, session=latest_session)

        # 1. Facts & Last Active
        self.assertEqual(ctx.last_app, "VS Code")
        self.assertEqual(ctx.last_entity, "summarizer.py")
        self.assertEqual(ctx.last_time, "21:49")
        self.assertEqual(ctx.primary_project, "Breadcrumb")

        # 2. Observed Facts
        observed_joined = " ".join(ctx.observed_facts)
        self.assertIn("summarizer.py", observed_joined)
        self.assertIn("VS Code was the final active application", observed_joined)

        # 3. Inferred Context & Explainability
        self.assertTrue(len(ctx.inferences) >= 1)
        self.assertIn("summarizer", ctx.inferences[0].lower())
        self.assertTrue(len(ctx.inferences_with_reasons) >= 1)
        self.assertTrue(len(ctx.inferences_with_reasons[0]["reasons"]) >= 1)

        # 4. Suggested Next Step
        self.assertIn("summarizer.py", ctx.suggested_next_step)

        # 5. Copyable Text Structure (Requirement 7)
        text = ctx.to_text()
        self.assertIn("Breadcrumb Resume Context", text)
        self.assertIn("Project:\nBreadcrumb", text)
        self.assertIn("Current context:", text)
        self.assertIn("Observed:", text)
        self.assertIn("Likely context:", text)
        self.assertIn("Suggested next step:", text)

    def test_legacy_auth_scenario(self):
        """Tests that a single-session authentication scenario still generates proper inferences."""
        events = [
            {"timestamp": "2026-09-30T10:41:00", "app_name": "VS Code", "window_title": "auth_service.py", "entity": "auth_service.py", "project": "agentdesk"},
            {"timestamp": "2026-09-30T10:47:00", "app_name": "Chrome", "window_title": "GitHub issue", "entity": "GitHub issue", "project": "agentdesk"},
            {"timestamp": "2026-09-30T10:51:00", "app_name": "Terminal", "window_title": "pytest", "entity": "pytest", "project": "agentdesk"},
            {"timestamp": "2026-09-30T10:57:00", "app_name": "VS Code", "window_title": "auth_service.py", "entity": "auth_service.py", "project": "agentdesk"},
        ]
        aggregated = TimelineAggregator.aggregate_events(events)
        ctx = RuleBasedSummarizer.summarize(aggregated)

        self.assertIn("VS Code", ctx.last_app)
        self.assertIn("auth_service.py", ctx.last_entity)
        self.assertIn("authentication", ctx.headline.lower())
        self.assertIn("auth_service.py", ctx.suggested_next_step)

    def test_empty_timeline(self):
        """Tests summarizer behavior on empty timeline."""
        ctx = RuleBasedSummarizer.summarize([])
        self.assertEqual(ctx.headline, "No recent activity recorded")
        self.assertEqual(len(ctx.activity_bullets), 0)

if __name__ == "__main__":
    unittest.main()
