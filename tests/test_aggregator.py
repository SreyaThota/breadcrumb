"""Unit tests for TimelineAggregator."""
import unittest
from breadcrumb.aggregator import TimelineAggregator

class TestTimelineAggregator(unittest.TestCase):
    def test_aggregate_consecutive_duplicates(self):
        """Ensures repeated consecutive events in the same app/file are collapsed into one block."""
        raw = [
            {"id": 1, "timestamp": "2026-09-30T10:41:00", "app_name": "VS Code", "window_title": "auth_service.py", "entity": "auth_service.py", "project": "agentdesk"},
            {"id": 2, "timestamp": "2026-09-30T10:42:00", "app_name": "VS Code", "window_title": "auth_service.py", "entity": "auth_service.py", "project": "agentdesk"},
            {"id": 3, "timestamp": "2026-09-30T10:43:00", "app_name": "VS Code", "window_title": "auth_service.py", "entity": "auth_service.py", "project": "agentdesk"},
            {"id": 4, "timestamp": "2026-09-30T10:47:00", "app_name": "Chrome", "window_title": "GitHub issue", "entity": "GitHub issue", "project": "agentdesk"},
            {"id": 5, "timestamp": "2026-09-30T10:51:00", "app_name": "Terminal", "window_title": "pytest", "entity": "pytest", "project": "agentdesk"},
        ]
        aggregated = TimelineAggregator.aggregate_events(raw)
        
        # 3 initial VS Code events should collapse to 1, followed by Chrome and Terminal -> total 3 steps
        self.assertEqual(len(aggregated), 3)
        self.assertEqual(aggregated[0]["app_name"], "VS Code")
        self.assertEqual(aggregated[0]["occurrences"], 3)
        self.assertEqual(aggregated[0]["start_time_label"], "10:41")
        self.assertEqual(aggregated[0]["last_time_label"], "10:43")

        self.assertEqual(aggregated[1]["app_name"], "Chrome")
        self.assertEqual(aggregated[1]["occurrences"], 1)

        self.assertEqual(aggregated[2]["app_name"], "Terminal")
        self.assertEqual(aggregated[2]["occurrences"], 1)

    def test_empty_events(self):
        self.assertEqual(TimelineAggregator.aggregate_events([]), [])

if __name__ == "__main__":
    unittest.main()
