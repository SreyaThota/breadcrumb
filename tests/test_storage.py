"""Unit tests for SQLite EventStore."""
import unittest
from pathlib import Path
import tempfile
import os

from breadcrumb.storage import EventStore

class TestEventStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_breadcrumb.db"
        self.store = EventStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_insert_and_query(self):
        self.assertEqual(self.store.count_events(), 0)
        
        self.store.insert_event(
            app_name="VS Code",
            window_title="auth_service.py - agentdesk",
            process_name="Code.exe",
            entity="auth_service.py",
            project="agentdesk"
        )
        self.assertEqual(self.store.count_events(), 1)

        events = self.store.get_recent_events(limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["app_name"], "VS Code")
        self.assertEqual(events[0]["entity"], "auth_service.py")

    def test_clear_all(self):
        self.store.insert_event("Chrome", "GitHub issue")
        self.store.insert_event("Terminal", "pytest")
        self.assertEqual(self.store.count_events(), 2)

        self.store.clear_all()
        self.assertEqual(self.store.count_events(), 0)

if __name__ == "__main__":
    unittest.main()
