"""Unit tests for WorkSession grouping, inactivity boundaries, duration calculation, and ignored apps."""
import unittest
from datetime import datetime
from breadcrumb.aggregator import TimelineAggregator, WorkSession

class TestWorkSessions(unittest.TestCase):
    def test_inactivity_boundary_groups_sessions(self):
        """Tests that events separated by > 15 minutes split into distinct sessions."""
        events = [
            # Session 1: 09:30 to 09:44
            {"timestamp": "2026-09-30T09:30:00", "app_name": "VS Code", "window_title": "main.py", "entity": "main.py", "project": "app"},
            {"timestamp": "2026-09-30T09:34:00", "app_name": "Chrome", "window_title": "Docs", "entity": "Docs", "project": "app"},
            {"timestamp": "2026-09-30T09:37:00", "app_name": "Terminal", "window_title": "pytest", "entity": "pytest", "project": "app"},
            {"timestamp": "2026-09-30T09:42:00", "app_name": "VS Code", "window_title": "main.py", "entity": "main.py", "project": "app"},
            {"timestamp": "2026-09-30T09:44:00", "app_name": "VS Code", "window_title": "main.py", "entity": "main.py", "project": "app"},
            # Inactivity gap: 36 minutes (09:44 to 10:20 > 15 min threshold)
            # Session 2: 10:20 to 10:35
            {"timestamp": "2026-09-30T10:20:00", "app_name": "Chrome", "window_title": "PR #1", "entity": "PR #1", "project": "app"},
            {"timestamp": "2026-09-30T10:35:00", "app_name": "VS Code", "window_title": "main.py", "entity": "main.py", "project": "app"},
        ]

        sessions = TimelineAggregator.group_into_sessions(events, inactivity_threshold_minutes=15)
        self.assertEqual(len(sessions), 2)

        s1 = sessions[0]
        self.assertEqual(s1.session_id, 1)
        self.assertEqual(s1.dominant_app, "VS Code")
        self.assertEqual(s1.start_time_label, "09:30")

        s2 = sessions[1]
        self.assertEqual(s2.session_id, 2)
        self.assertEqual(s2.start_time_label, "10:20")

    def test_duration_calculation(self):
        """Verifies that active duration per application is calculated in minutes."""
        events = [
            {"timestamp": "2026-09-30T14:00:00", "app_name": "VS Code", "window_title": "api.py", "entity": "api.py"},
            {"timestamp": "2026-09-30T14:20:00", "app_name": "Chrome", "window_title": "API Spec", "entity": "API Spec"},
            {"timestamp": "2026-09-30T14:25:00", "app_name": "Terminal", "window_title": "curl", "entity": "curl"},
        ]
        sessions = TimelineAggregator.group_into_sessions(events, inactivity_threshold_minutes=30)
        self.assertEqual(len(sessions), 1)

        s = sessions[0]
        app_names = [a for a, _, _, _ in s.app_durations]
        self.assertIn("VS Code", app_names)
        self.assertIn("Chrome", app_names)
        self.assertIn("Terminal", app_names)

        # VS Code dwell from 14:00 to 14:20 = 20 mins
        vs_code_entry = next(entry for entry in s.app_durations if entry[0] == "VS Code")
        self.assertGreaterEqual(vs_code_entry[1], 15)
        self.assertEqual(s.dominant_app, "VS Code")

    def test_ignored_applications(self):
        """Verifies that ignored applications (Spotify, WhatsApp) are excluded from sessions."""
        events = [
            {"timestamp": "2026-09-30T11:00:00", "app_name": "VS Code", "window_title": "code.py", "entity": "code.py"},
            {"timestamp": "2026-09-30T11:05:00", "app_name": "Spotify", "window_title": "Music", "entity": "Music"},
            {"timestamp": "2026-09-30T11:10:00", "app_name": "WhatsApp", "window_title": "Chat", "entity": "Chat"},
            {"timestamp": "2026-09-30T11:12:00", "app_name": "VS Code", "window_title": "code.py", "entity": "code.py"},
        ]
        sessions = TimelineAggregator.group_into_sessions(
            events,
            inactivity_threshold_minutes=15,
            ignored_apps=["Spotify", "WhatsApp"]
        )
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        apps_in_session = [a for a, _, _, _ in s.app_durations]
        self.assertNotIn("Spotify", apps_in_session)
        self.assertNotIn("WhatsApp", apps_in_session)
        self.assertIn("VS Code", apps_in_session)

    def test_timeline_search_filtering(self):
        """Tests deterministic keyword search over events."""
        events = [
            {"timestamp": "2026-09-30T09:00:00", "app_name": "VS Code", "window_title": "summarizer.py", "entity": "summarizer.py", "project": "Breadcrumb"},
            {"timestamp": "2026-09-30T09:10:00", "app_name": "Chrome", "window_title": "GitHub PR", "entity": "PR", "project": "Breadcrumb"},
            {"timestamp": "2026-09-30T09:20:00", "app_name": "Terminal", "window_title": "pytest", "entity": "pytest", "project": "Breadcrumb"},
        ]

        # Search by file
        res_file = TimelineAggregator.filter_events(events, "summarizer.py")
        self.assertEqual(len(res_file), 1)
        self.assertEqual(res_file[0]["app_name"], "VS Code")

        # Search by app
        res_app = TimelineAggregator.filter_events(events, "Chrome")
        self.assertEqual(len(res_app), 1)
        self.assertEqual(res_app[0]["app_name"], "Chrome")

        # Search by command
        res_cmd = TimelineAggregator.filter_events(events, "pytest")
        self.assertEqual(len(res_cmd), 1)

        # Empty search returns all
        self.assertEqual(len(TimelineAggregator.filter_events(events, "")), 3)

if __name__ == "__main__":
    unittest.main()
