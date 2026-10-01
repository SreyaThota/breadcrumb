"""Timeline Aggregator and Sessionization for Breadcrumb.

Groups consecutive micro-events into meaningful, readable timeline steps.
Partitions activity events into distinct Work Sessions separated by inactivity boundaries.
Calculates approximate active time per application and extracts flow narratives.
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
import config

class WorkSession:
    """Represents a discrete, cohesive block of focused work."""
    def __init__(
        self,
        session_id: int,
        start_dt: datetime,
        end_dt: datetime,
        events: List[Dict[str, Any]],
        app_durations: List[Tuple[str, int, str, int]],
        dominant_app: str,
        workspace: Optional[str],
        flow: List[str],
    ):
        self.session_id = session_id
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.events = events
        self.app_durations = app_durations  # (app_name, minutes, "Xm", event_count)
        self.dominant_app = dominant_app
        self.workspace = workspace
        self.flow = flow

        # Calculate total duration in minutes
        total_delta = int((end_dt - start_dt).total_seconds() / 60)
        # Ensure at least 1 minute
        self.duration_minutes = max(1, total_delta)

        self.start_time_label = start_dt.strftime("%H:%M")
        self.end_time_label = end_dt.strftime("%H:%M")
        self.time_span_label = f"{self.start_time_label} – {self.end_time_label}"
        self.flow_text = " -> ".join(flow) if flow else dominant_app

    @property
    def last_event(self) -> Optional[Dict[str, Any]]:
        return self.events[-1] if self.events else None


class TimelineAggregator:
    @staticmethod
    def parse_datetime(iso_str: str) -> datetime:
        """Robust parser for ISO timestamp strings."""
        try:
            return datetime.fromisoformat(iso_str)
        except Exception:
            # Fallback if time only or format variant
            today = date.today()
            if "T" in iso_str:
                parts = iso_str.split("T")
                d_parts = [int(p) for p in parts[0].split("-")]
                t_parts = [int(p) for p in parts[1].split(":")[:2]]
                return datetime(d_parts[0], d_parts[1], d_parts[2], t_parts[0], t_parts[1])
            elif ":" in iso_str:
                t_parts = [int(p) for p in iso_str.split(":")[:2]]
                return datetime(today.year, today.month, today.day, t_parts[0], t_parts[1])
            return datetime.now()

    @staticmethod
    def format_time_label(iso_str: str) -> str:
        """Extracts HH:MM from ISO timestamp string."""
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%H:%M")
        except Exception:
            if "T" in iso_str:
                return iso_str.split("T")[1][:5]
            return iso_str[:5] if len(iso_str) >= 5 else iso_str

    @classmethod
    def aggregate_events(
        cls,
        raw_events: List[Dict[str, Any]],
        ignored_apps: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Compresses consecutive duplicate events and filters transient micro-switches.
        Excludes any events matching ignored_apps.
        """
        if not raw_events:
            return []

        ignored_set = {app.strip().lower() for app in (ignored_apps or []) if app.strip()}

        aggregated: List[Dict[str, Any]] = []

        for ev in raw_events:
            app_name = ev.get("app_name") or "Unknown"
            # Filter ignored applications
            if app_name.lower() in ignored_set:
                continue

            window_title = ev.get("window_title") or ""
            entity = ev.get("entity") or window_title
            project = ev.get("project")
            timestamp = ev.get("timestamp") or ""
            time_label = cls.format_time_label(timestamp)

            if entity and entity != app_name:
                display_desc = entity
            else:
                display_desc = window_title

            # Check if this continues the immediately preceding activity
            if aggregated and aggregated[-1]["app_name"] == app_name and aggregated[-1]["entity"] == entity:
                aggregated[-1]["occurrences"] += 1
                aggregated[-1]["last_timestamp"] = timestamp
                aggregated[-1]["last_time_label"] = time_label
            else:
                aggregated.append({
                    "id": ev.get("id"),
                    "start_timestamp": timestamp,
                    "start_time_label": time_label,
                    "last_timestamp": timestamp,
                    "last_time_label": time_label,
                    "app_name": app_name,
                    "window_title": window_title,
                    "entity": entity,
                    "project": project,
                    "description": display_desc,
                    "occurrences": 1,
                    "duration_seconds": ev.get("duration_seconds", 0.0),
                })

        return aggregated

    @classmethod
    def group_into_sessions(
        cls,
        raw_events: List[Dict[str, Any]],
        inactivity_threshold_minutes: int = config.SESSION_INACTIVITY_THRESHOLD_MINUTES,
        ignored_apps: Optional[List[str]] = None
    ) -> List[WorkSession]:
        """
        Groups activity events into distinct Work Sessions separated by inactivity boundaries.
        Calculates approximate active time per application for each session.
        """
        # First filter ignored apps and sort chronologically
        ignored_set = {app.strip().lower() for app in (ignored_apps or []) if app.strip()}
        valid_events = [
            e for e in raw_events
            if (e.get("app_name") or "").lower() not in ignored_set
        ]

        if not valid_events:
            return []

        # Sort events by timestamp ascending
        sorted_events = sorted(
            valid_events,
            key=lambda e: cls.parse_datetime(e.get("timestamp") or "")
        )

        session_buckets: List[List[Dict[str, Any]]] = []
        current_bucket: List[Dict[str, Any]] = [sorted_events[0]]

        inactivity_gap = timedelta(minutes=inactivity_threshold_minutes)

        for i in range(1, len(sorted_events)):
            prev_ev = sorted_events[i - 1]
            curr_ev = sorted_events[i]

            prev_dt = cls.parse_datetime(prev_ev.get("timestamp") or "")
            curr_dt = cls.parse_datetime(curr_ev.get("timestamp") or "")

            gap = curr_dt - prev_dt
            if gap > inactivity_gap:
                # Boundary detected: start a new session bucket
                session_buckets.append(current_bucket)
                current_bucket = [curr_ev]
            else:
                current_bucket.append(curr_ev)

        if current_bucket:
            session_buckets.append(current_bucket)

        # Convert buckets into WorkSession objects
        sessions: List[WorkSession] = []
        for idx, bucket in enumerate(session_buckets, start=1):
            sess = cls._build_session(idx, bucket, inactivity_threshold_minutes)
            sessions.append(sess)

        return sessions

    @classmethod
    def _build_session(
        cls,
        session_id: int,
        events: List[Dict[str, Any]],
        inactivity_threshold_minutes: int
    ) -> WorkSession:
        """Computes durations, dominant app, flow, and workspace for a single session."""
        start_dt = cls.parse_datetime(events[0].get("timestamp") or "")
        
        # Calculate approximate active duration per application
        app_minutes = defaultdict(float)
        app_event_counts = Counter()

        for i in range(len(events)):
            ev = events[i]
            app = ev.get("app_name") or "Unknown"
            app_event_counts[app] += 1

            curr_dt = cls.parse_datetime(ev.get("timestamp") or "")

            if i < len(events) - 1:
                next_dt = cls.parse_datetime(events[i + 1].get("timestamp") or "")
                delta_mins = max(1.0, (next_dt - curr_dt).total_seconds() / 60.0)
                # Cap at inactivity threshold to avoid skewing
                delta_mins = min(delta_mins, float(inactivity_threshold_minutes))
            else:
                # Last event in session: use recorded duration or default estimate
                rec_secs = ev.get("duration_seconds", 0.0)
                if rec_secs and rec_secs > 30:
                    delta_mins = max(1.0, round(rec_secs / 60.0, 1))
                else:
                    delta_mins = 3.0  # reasonable final dwell time

            app_minutes[app] += delta_mins

        last_ev_dt = cls.parse_datetime(events[-1].get("timestamp") or "")
        # End time = last event timestamp + final dwell duration
        final_dwell = min(app_minutes[events[-1].get("app_name") or "Unknown"], 5.0)
        end_dt = last_ev_dt + timedelta(minutes=int(final_dwell))

        # Format app durations sorted by time spent descending
        sorted_apps = sorted(app_minutes.items(), key=lambda x: x[1], reverse=True)
        app_durations: List[Tuple[str, int, str, int]] = []
        for app_name, mins in sorted_apps:
            int_mins = max(1, int(round(mins)))
            app_durations.append((app_name, int_mins, f"{int_mins}m", app_event_counts[app_name]))

        dominant_app = sorted_apps[0][0] if sorted_apps else "Unknown"

        # Build chronological transition flow (e.g. VS Code -> Chrome -> Terminal -> VS Code)
        flow: List[str] = []
        for ev in events:
            app = ev.get("app_name") or "Unknown"
            if not flow or flow[-1] != app:
                flow.append(app)

        # Detect primary workspace/project if present
        projects = [e.get("project") for e in events if e.get("project")]
        workspace = Counter(projects).most_common(1)[0][0] if projects else None

        # Build aggregated representation of session events
        aggregated_session_events = cls.aggregate_events(events)

        return WorkSession(
            session_id=session_id,
            start_dt=start_dt,
            end_dt=end_dt,
            events=aggregated_session_events,
            app_durations=app_durations,
            dominant_app=dominant_app,
            workspace=workspace,
            flow=flow,
        )

    @classmethod
    def filter_events(cls, events: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Fast deterministic search over timeline events.
        Matches app name, entity, window title, project, or timestamp.
        """
        if not query or not query.strip():
            return events

        q = query.strip().lower()
        results = []
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()

        for e in events:
            app = (e.get("app_name") or "").lower()
            title = (e.get("window_title") or "").lower()
            entity = (e.get("entity") or "").lower()
            project = (e.get("project") or "").lower()
            ts = (e.get("timestamp") or "").lower()

            # Date keyword matching
            if q == "today" and today_str in ts:
                results.append(e)
                continue
            if q == "yesterday" and yesterday_str in ts:
                results.append(e)
                continue

            if q in app or q in title or q in entity or q in project or q in ts:
                results.append(e)

        return results

    @classmethod
    def format_timeline_lines(cls, aggregated_events: List[Dict[str, Any]]) -> List[str]:
        """Formats aggregated events into clean strings for the UI timeline."""
        lines = []
        for item in aggregated_events:
            time_part = item["start_time_label"].ljust(6)
            app_part = item["app_name"].ljust(12)
            desc_part = item["description"]
            lines.append(f"{time_part} {app_part} — {desc_part}")
        return lines
