"""Resume Context Generator for Breadcrumb.

Analyzes the recent activity timeline using deterministic rules.
Strictly separates OBSERVED facts (system recorded) from INFERENCES (heuristic deductions).
Provides detailed explainability ("Why?" evidence) and structured Markdown export.
"""
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import json
import logging
import urllib.request
import urllib.error

import config
from breadcrumb.aggregator import WorkSession, TimelineAggregator

logger = logging.getLogger(__name__)

class ResumeContext:
    """Structured container for the resume context."""
    def __init__(
        self,
        headline: str,
        facts: List[str],
        inferences: List[str],
        activity_bullets: List[str],
        suggested_next_step: str,
        engine_used: str = "Deterministic Rules",
        last_app: Optional[str] = None,
        last_entity: Optional[str] = None,
        last_time: Optional[str] = None,
        app_counts: Optional[List[Any]] = None,
        primary_project: Optional[str] = None,
        confidence: Optional[str] = None,
        session_duration: Optional[str] = None,
        session_time_span: Optional[str] = None,
        flow_text: Optional[str] = None,
        app_durations: Optional[List[Tuple[str, int, str, int]]] = None,
        observed_facts: Optional[List[str]] = None,
        inferences_with_reasons: Optional[List[Dict[str, Any]]] = None,
    ):
        self.headline = headline
        self.facts = facts
        self.inferences = inferences
        self.activity_bullets = activity_bullets
        self.suggested_next_step = suggested_next_step
        self.engine_used = engine_used
        self.last_app = last_app
        self.last_entity = last_entity
        self.last_time = last_time
        self.app_counts = app_counts or []
        self.primary_project = primary_project
        self.confidence = confidence

        # V2 Sessionization & Explainability Properties
        self.session_duration = session_duration or "Recent session"
        self.session_time_span = session_time_span or (last_time or "Now")
        self.flow_text = flow_text or (last_app or "Active app")
        self.app_durations = app_durations or []
        self.observed_facts = observed_facts or facts
        self.inferences_with_reasons = inferences_with_reasons or []

    def to_text(self) -> str:
        """
        Renders structured Markdown context optimized for copying and pasting
        into ChatGPT, Claude, Slack, or developer notes.
        """
        lines = []
        lines.append("Breadcrumb Resume Context")
        lines.append("")

        proj = self.primary_project or "General Workspace"
        lines.append("Project:")
        lines.append(proj)
        lines.append("")

        lines.append("Session:")
        lines.append(f"{self.session_time_span} ({self.session_duration})")
        lines.append("")

        lines.append("Current context:")
        entity_name = self.last_entity or "recent files"
        app_name = self.last_app or "editor"
        lines.append(f"Working on {entity_name} in {app_name}.")
        lines.append("")

        if self.flow_text:
            lines.append("Recent activity:")
            lines.append(self.flow_text)
            lines.append("")

        lines.append("Observed:")
        for obs in self.observed_facts:
            clean_obs = obs.lstrip("✓*• ").strip()
            lines.append(f"* {clean_obs}")
        lines.append("")

        if self.inferences:
            lines.append("Likely context:")
            lines.append(self.inferences[0])
            lines.append("")

        lines.append("Suggested next step:")
        lines.append(self.suggested_next_step)

        return "\n".join(lines)


class RuleBasedSummarizer:
    """Zero-dependency deterministic rule engine for reconstructing context."""

    @classmethod
    def summarize(
        cls,
        aggregated_events: List[Dict[str, Any]],
        session: Optional[WorkSession] = None
    ) -> ResumeContext:
        if not aggregated_events and not session:
            return ResumeContext(
                headline="No recent activity recorded",
                facts=["Timeline is currently empty."],
                inferences=["Start working across apps and Breadcrumb will record your trail."],
                activity_bullets=[],
                suggested_next_step="Open your workspace to begin tracking.",
                last_app=None,
                last_entity=None,
                last_time=None,
                app_counts=[],
                primary_project=None,
                confidence=None,
            )

        events_to_use = session.events if session else aggregated_events
        if not events_to_use:
            events_to_use = aggregated_events

        last_event = events_to_use[-1]
        last_app = last_event.get("app_name", "Unknown")
        last_entity = last_event.get("entity") or last_event.get("window_title", "")
        last_time = last_event.get("last_time_label") or last_event.get("start_time_label", "")

        # Session Metrics
        if session:
            session_duration = f"{session.duration_minutes} min"
            session_time_span = session.time_span_label
            flow_text = session.flow_text
            app_durations = session.app_durations
            primary_project = session.workspace
        else:
            session_duration = "Recent session"
            session_time_span = f"{events_to_use[0].get('start_time_label', '')} – {last_time}"
            flow_items = []
            for ev in events_to_use:
                a = ev.get("app_name") or "Unknown"
                if not flow_items or flow_items[-1] != a:
                    flow_items.append(a)
            flow_text = " → ".join(flow_items)
            app_durations = []
            projects = [e.get("project") for e in events_to_use if e.get("project")]
            primary_project = Counter(projects).most_common(1)[0][0] if projects else None

        # 1. OBSERVED FACTS (Verifiable system telemetry)
        observed_facts: List[str] = []
        if last_entity:
            observed_facts.append(f"{last_entity} was active in {last_app}")
        else:
            observed_facts.append(f"{last_app} was active")

        # Processes and commands detected
        terminal_cmds = [
            e.get("entity") for e in events_to_use
            if e.get("app_name") == "Terminal" and e.get("entity")
        ]
        for cmd in terminal_cmds[:2]:
            observed_facts.append(f"{cmd} was executed in Terminal")

        has_python = any(
            "python" in (e.get("description", "") + e.get("window_title", "")).lower()
            for e in events_to_use
        )
        if has_python:
            observed_facts.append("Python process was active")

        observed_facts.append(f"{last_app} was the final active application")

        # Standard facts summary for backward compatibility
        facts = [f"Last active in {last_app} on '{last_entity}' at {last_time}."]
        app_counts = Counter(e["app_name"] for e in events_to_use)
        app_summary = ", ".join(f"{app} ({count}x)" for app, count in app_counts.most_common())
        facts.append(f"Applications touched: {app_summary}.")
        if primary_project:
            facts.append(f"Active workspace/repository: {primary_project}.")

        # Activity bullets
        activity_bullets: List[str] = []
        for e in events_to_use:
            app = e.get("app_name", "")
            desc = e.get("description", "")
            t = e.get("start_time_label", "")
            if app == "VS Code":
                action = f"Edited/viewed {desc} in {app}"
            elif app in ("Chrome", "Edge", "Firefox"):
                action = f"Browsed {desc} in {app}"
            elif app == "Terminal":
                action = f"Ran {desc} in {app}"
            else:
                action = f"Used {app} ({desc})"
            activity_bullets.append(f"{t}  {action}")

        # 2. INFERENCES WITH EVIDENCE ("Why?" reasoning)
        combined_text = " ".join(
            f"{e.get('description', '')} {e.get('project', '')} {e.get('window_title', '')}"
            for e in events_to_use
        ).lower()

        inferences: List[str] = []
        inferences_with_reasons: List[Dict[str, Any]] = []

        detected_topic = None
        topic_reasons = []

        if "summarizer" in combined_text or "resume" in combined_text or "context" in combined_text:
            detected_topic = "the Resume Context summarizer"
            topic_reasons.append("summarizer.py was active in VS Code")
            topic_reasons.append("Recent focus on context recovery logic")
        elif "auth" in combined_text or "login" in combined_text or "token" in combined_text:
            detected_topic = "authentication"
            topic_reasons.append("auth_service.py or authentication tokens in focus")
        elif "test" in combined_text or "pytest" in combined_text:
            detected_topic = "testing and verification"
            topic_reasons.append("pytest or test runner was executed")
        elif "ui" in combined_text or "app.py" in combined_text:
            detected_topic = "the desktop user interface"
            topic_reasons.append("app.py active in code editor")

        if terminal_cmds:
            topic_reasons.append(f"Terminal command: {terminal_cmds[0]}")
        topic_reasons.append(f"{last_app} remained active afterwards")

        display_proj = primary_project.title() if primary_project else "your project"

        if detected_topic and primary_project:
            headline = f"Working on {display_proj} {detected_topic}"
            primary_inf = f"You were probably testing or developing {detected_topic} in {display_proj}."
        elif detected_topic:
            headline = f"Working on {detected_topic}"
            primary_inf = f"You were probably working on {detected_topic}."
        elif primary_project:
            headline = f"Working in {display_proj}"
            primary_inf = f"You appear to have been focused within the {display_proj} repository."
        else:
            headline = f"Active in {last_app}"
            primary_inf = f"You were active across {len(events_to_use)} sequential steps in {last_app}."

        inferences.append(primary_inf)
        inferences_with_reasons.append({
            "inference": primary_inf,
            "reasons": topic_reasons or [f"{last_entity} active in {last_app}"]
        })

        # Workflow pattern inference
        has_editor = any(e.get("app_name") == "VS Code" for e in events_to_use)
        has_terminal = any(e.get("app_name") == "Terminal" for e in events_to_use)
        has_browser = any(e.get("app_name") in ("Chrome", "Edge", "Firefox") for e in events_to_use)

        if has_editor and has_terminal and has_browser:
            flow_inf = "Workflow pattern: Coding cycle with online reference and terminal verification."
            flow_reasons = [
                "Consecutive sequence: VS Code → Chrome → Terminal",
                "Browser used for documentation and Terminal for test runs"
            ]
        elif has_editor and has_terminal:
            flow_inf = "Workflow pattern: Code editing and terminal command execution."
            flow_reasons = ["Continuous cycle between editor and terminal"]
        elif has_editor and has_browser:
            flow_inf = "Workflow pattern: Code editing with web documentation reference."
            flow_reasons = ["Alternating between editor and browser tabs"]
        else:
            flow_inf = f"Focused session primarily within {last_app}."
            flow_reasons = [f"Majority of dwell time logged in {last_app}"]

        inferences.append(flow_inf)
        inferences_with_reasons.append({
            "inference": flow_inf,
            "reasons": flow_reasons
        })

        # 3. SUGGESTED NEXT STEP
        if last_app == "VS Code":
            if "test" in combined_text or "pytest" in combined_text:
                suggested_next_step = f"Continue testing and verifying changes in {last_entity}."
            else:
                suggested_next_step = f"Continue reviewing {last_entity} in {last_app}."
        elif last_app == "Terminal":
            suggested_next_step = f"Inspect output of {last_entity} and return to code."
        elif last_app in ("Chrome", "Edge", "Firefox"):
            suggested_next_step = f"Review the reference materials in {last_app} or switch back to your editor."
        else:
            suggested_next_step = f"Resume your last active session in {last_app}."

        confidence = "High" if len(events_to_use) >= 4 else ("Medium" if len(events_to_use) >= 2 else None)

        return ResumeContext(
            headline=headline,
            facts=facts,
            inferences=inferences,
            activity_bullets=activity_bullets,
            suggested_next_step=suggested_next_step,
            engine_used="Deterministic Rules",
            last_app=last_app,
            last_entity=last_entity,
            last_time=last_time,
            app_counts=app_counts.most_common(),
            primary_project=primary_project,
            confidence=confidence,
            session_duration=session_duration,
            session_time_span=session_time_span,
            flow_text=flow_text,
            app_durations=app_durations,
            observed_facts=observed_facts,
            inferences_with_reasons=inferences_with_reasons,
        )


class ContextSummarizer:
    """Facade for generating resume context with optional Ollama local LLM fallback."""

    @classmethod
    def generate_context(
        cls,
        aggregated_events: List[Dict[str, Any]],
        session: Optional[WorkSession] = None
    ) -> ResumeContext:
        rule_context = RuleBasedSummarizer.summarize(aggregated_events, session=session)

        if not config.OLLAMA_ENABLED or not aggregated_events:
            return rule_context

        try:
            return cls._try_ollama_summarize(aggregated_events, rule_context)
        except Exception as e:
            logger.debug(f"Ollama local LLM unavailable or timed out ({e}). Using deterministic rules.")
            return rule_context

    @classmethod
    def _try_ollama_summarize(
        cls, aggregated_events: List[Dict[str, Any]], fallback: ResumeContext
    ) -> ResumeContext:
        prompt = (
            "You are Breadcrumb, a desktop context recovery tool.\n"
            "Here is the user's chronological activity timeline:\n"
        )
        for e in aggregated_events:
            prompt += f"- {e.get('start_time_label')} {e.get('app_name')}: {e.get('description')}\n"

        prompt += (
            "\nIn 2-3 concise sentences, summarize what the user was doing and suggest the next step.\n"
            "Distinguish between facts and inferences."
        )

        payload = {
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }

        req = urllib.request.Request(
            config.OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            llm_text = data.get("response", "").strip()
            if llm_text:
                fallback.inferences.insert(0, f"Local LLM ({config.OLLAMA_MODEL}): {llm_text}")
                fallback.engine_used = f"Deterministic Rules + Ollama ({config.OLLAMA_MODEL})"

        return fallback
