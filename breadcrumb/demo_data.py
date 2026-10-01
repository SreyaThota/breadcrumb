"""Demo Data Generator for Breadcrumb V2.

Provides realistic multi-session activity data demonstrating:
  Session 1 (20:40 – 21:01): Initial implementation and test verification
  [Inactivity Gap: 19 minutes]
  Session 2 (21:20 – 21:49): UI refinement and context summarizer testing
"""
from typing import List, Dict, Any
from datetime import date
from breadcrumb.storage import EventStore

def get_demo_events() -> List[Dict[str, Any]]:
    """Returns realistic multi-session activity events."""
    today = date.today().isoformat()
    return [
        # --- SESSION 1: 20:40 – 21:01 (21 min) ---
        {
            "timestamp": f"{today}T20:40:00",
            "app_name": "VS Code",
            "window_title": "summarizer.py - breadcrumb - Visual Studio Code",
            "process_name": "Code.exe",
            "entity": "summarizer.py",
            "project": "Breadcrumb",
            "duration_seconds": 480.0,
        },
        {
            "timestamp": f"{today}T20:48:00",
            "app_name": "Chrome",
            "window_title": "Python datetime & timedelta documentation - Google Chrome",
            "process_name": "chrome.exe",
            "entity": "Python documentation",
            "project": "Documentation",
            "duration_seconds": 300.0,
        },
        {
            "timestamp": f"{today}T20:53:00",
            "app_name": "Terminal",
            "window_title": "Windows PowerShell - pytest tests/test_summarizer.py",
            "process_name": "powershell.exe",
            "entity": "pytest",
            "project": "Breadcrumb",
            "duration_seconds": 480.0,
        },
        {
            "timestamp": f"{today}T21:01:00",
            "app_name": "VS Code",
            "window_title": "summarizer.py - breadcrumb - Visual Studio Code",
            "process_name": "Code.exe",
            "entity": "summarizer.py",
            "project": "Breadcrumb",
            "duration_seconds": 240.0,
        },

        # --- [19-minute inactivity gap: 21:01 to 21:20] ---

        # --- SESSION 2: 21:20 – 21:49 (29 min) ---
        {
            "timestamp": f"{today}T21:20:00",
            "app_name": "VS Code",
            "window_title": "app.py - breadcrumb - Visual Studio Code",
            "process_name": "Code.exe",
            "entity": "app.py",
            "project": "Breadcrumb",
            "duration_seconds": 480.0,
        },
        {
            "timestamp": f"{today}T21:28:00",
            "app_name": "Chrome",
            "window_title": "Tkinter Canvas Scrollable Window Reference - Google Chrome",
            "process_name": "chrome.exe",
            "entity": "UI reference",
            "project": "Documentation",
            "duration_seconds": 420.0,
        },
        {
            "timestamp": f"{today}T21:35:00",
            "app_name": "VS Code",
            "window_title": "app.py - breadcrumb - Visual Studio Code",
            "process_name": "Code.exe",
            "entity": "app.py",
            "project": "Breadcrumb",
            "duration_seconds": 840.0,
        },
        {
            "timestamp": f"{today}T21:49:00",
            "app_name": "VS Code",
            "window_title": "summarizer.py - breadcrumb - Visual Studio Code",
            "process_name": "Code.exe",
            "entity": "summarizer.py",
            "project": "Breadcrumb",
            "duration_seconds": 180.0,
        },
    ]

def load_demo_events(storage: EventStore):
    """Loads multi-session demo events into the local EventStore."""
    storage.clear_all()
    for ev in get_demo_events():
        storage.insert_event(
            app_name=ev["app_name"],
            window_title=ev["window_title"],
            process_name=ev["process_name"],
            entity=ev["entity"],
            project=ev["project"],
            timestamp=ev["timestamp"],
            duration_seconds=ev["duration_seconds"],
        )
