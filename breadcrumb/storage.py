"""Local SQLite Event Store for Breadcrumb.

All data remains strictly on the local machine. No external transmission.
"""
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class EventStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-safe connection to the SQLite database."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes database schema with indexing."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS activity_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        app_name TEXT NOT NULL,
                        window_title TEXT NOT NULL,
                        process_name TEXT,
                        entity TEXT,
                        project TEXT,
                        duration_seconds REAL DEFAULT 0.0
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON activity_events(timestamp)
                """)
        finally:
            conn.close()

    def insert_event(
        self,
        app_name: str,
        window_title: str,
        process_name: Optional[str] = None,
        entity: Optional[str] = None,
        project: Optional[str] = None,
        timestamp: Optional[str] = None,
        duration_seconds: float = 0.0
    ) -> int:
        """Inserts a single activity event into the database."""
        if not timestamp:
            timestamp = datetime.now().isoformat(timespec="seconds")
        
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO activity_events 
                    (timestamp, app_name, window_title, process_name, entity, project, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, app_name, window_title, process_name, entity, project, duration_seconds)
                )
                return cursor.lastrowid
        finally:
            conn.close()

    def get_recent_events(self, limit: int = 50, since_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent events ordered chronologically (oldest to newest for analysis)."""
        conn = self._get_connection()
        try:
            if since_iso:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, app_name, window_title, process_name, entity, project, duration_seconds
                    FROM activity_events
                    WHERE timestamp >= ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (since_iso, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, app_name, window_title, process_name, entity, project, duration_seconds
                    FROM activity_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]
        finally:
            conn.close()

    def clear_all(self):
        """Wipes all local activity events completely."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM activity_events")
            logger.info("Cleared all activity history.")
        finally:
            conn.close()

    def count_events(self) -> int:
        """Returns the total number of recorded events."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM activity_events")
            return cursor.fetchone()[0]
        finally:
            conn.close()
