#!/usr/bin/env python3
"""Breadcrumb Entry Point.

Usage:
    python run.py              # Launch the native desktop application
    python run.py --demo       # Run instant demo scenario in console
    python run.py --status     # View current recorded local events
    python run.py --clear      # Wipe local database history
"""
import sys
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure package root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from breadcrumb.storage import EventStore
from breadcrumb.demo_data import load_demo_events, get_demo_events
from breadcrumb.aggregator import TimelineAggregator
from breadcrumb.summarizer import ContextSummarizer

def run_demo_cli():
    print("=" * 60)
    print(" BREADCRUMB - DEMO SCENARIO EVALUATION")
    print(" Tagline: 'Your computer remembers where your brain stopped.'")
    print("=" * 60)
    print("\n[1] Loading multi-session sample activity:")
    
    events = get_demo_events()
    sessions = TimelineAggregator.group_into_sessions(events)

    for s in sessions:
        print(f"\n  • Work Session {s.session_id}: {s.time_span_label} ({s.duration_minutes} min)")
        print(f"    Flow: {s.flow_text}")
        for ev in s.events:
            print(f"      {ev['start_time_label']}  {ev['app_name'].ljust(10)} - {ev['description']}")

    latest_session = sessions[-1] if sessions else None
    print(f"\n[2] User action: Clicking 'What was I doing?' on latest session (Session {latest_session.session_id})...")
    ctx = ContextSummarizer.generate_context(latest_session.events if latest_session else events, session=latest_session)

    print("\n" + ctx.to_text())
    print("\n[✓] Demo analysis completed successfully.")

def show_status_cli(storage: EventStore):
    count = storage.count_events()
    print(f"Breadcrumb Local Storage: {config.DB_PATH}")
    print(f"Total events recorded: {count}")
    if count > 0:
        print("\nRecent 10 events:")
        recent = storage.get_recent_events(limit=10)
        aggregated = TimelineAggregator.aggregate_events(recent)
        for line in TimelineAggregator.format_timeline_lines(aggregated):
            print(f"  {line}")

def clear_cli(storage: EventStore):
    storage.clear_all()
    print("Breadcrumb: Local activity history cleared.")

def main():
    parser = argparse.ArgumentParser(description="Breadcrumb desktop productivity tool.")
    parser.add_argument("--demo", action="store_true", help="Run the demo scenario in terminal")
    parser.add_argument("--status", action="store_true", help="Print local storage status and recent events")
    parser.add_argument("--clear", action="store_true", help="Wipe local database history")
    args = parser.parse_args()

    storage = EventStore(config.DB_PATH)

    if args.demo:
        run_demo_cli()
        return

    if args.status:
        show_status_cli(storage)
        return

    if args.clear:
        clear_cli(storage)
        return

    # Default: launch desktop Tkinter GUI
    from breadcrumb.app import start_gui
    start_gui()

if __name__ == "__main__":
    main()
