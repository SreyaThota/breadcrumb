"""Breadcrumb Desktop Application (Tkinter) - V2.

Session-oriented context recovery tool.
Answers: "What was I doing, where did I stop, and how can I continue?"
All processing and data storage remain 100% local.
"""
import sys
import tkinter as tk
from tkinter import messagebox
import logging
from typing import Optional, Dict, Any, List, Tuple

import config
from breadcrumb.storage import EventStore
from breadcrumb.collector import ActivityCollector
from breadcrumb.aggregator import TimelineAggregator, WorkSession
from breadcrumb.summarizer import ContextSummarizer, ResumeContext
from breadcrumb.demo_data import load_demo_events

logger = logging.getLogger(__name__)

APP_ICONS = {
    "VS Code": "💻",
    "Antigravity IDE": "🚀",
    "Chrome": "🌐",
    "Edge": "🌐",
    "Firefox": "🌐",
    "Brave": "🌐",
    "Terminal": "⌨",
    "Python": "🐍",
    "File Explorer": "📁",
    "Windows Settings": "⚙",
    "Windows Shell": "🖥",
    "Slack": "💬",
    "Discord": "💬",
    "Teams": "👥",
    "Acrobat Reader": "📄",
    "Notepad": "📝",
    "Protected Application": "🔒",
}

def get_app_icon(app_name: str) -> str:
    return APP_ICONS.get(app_name, "▫")

def truncate_text(text: str, max_chars: int = 38) -> str:
    if not text:
        return ""
    return text[:max_chars - 3] + "..." if len(text) > max_chars else text

def try_focus_window(target_app: str, target_entity: str) -> bool:
    """Attempts to bring target application to the foreground on Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        found_hwnd = None

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def enum_cb(hwnd, lparam):
            nonlocal found_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if (target_entity and target_entity.lower() in title.lower()) or (target_app and target_app.lower() in title.lower()):
                    if not title.startswith("Breadcrumb"):
                        found_hwnd = hwnd
                        return False
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        if found_hwnd:
            user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(found_hwnd)
            return True
    except Exception as e:
        logger.debug(f"Window focus attempt: {e}")
    return False


class ScrollableFrame(tk.Frame):
    """Clean vertical scrollable frame for Tkinter."""
    def __init__(self, parent, bg="#ffffff", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_content = tk.Frame(self.canvas, bg=bg)

        self.scrollable_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class BreadcrumbApp(tk.Tk):
    def __init__(self, storage: Optional[EventStore] = None):
        super().__init__()
        self.title("Breadcrumb — Resume Work Context")
        self.geometry("940x740")
        self.minsize(820, 600)
        self.configure(bg="#f8fafc")

        # Storage and Collector
        self.storage = storage or EventStore(config.DB_PATH)
        self.collector = ActivityCollector(
            storage=self.storage,
            on_event_callback=self._on_live_event
        )

        self.current_context: Optional[ResumeContext] = None
        self.latest_session: Optional[WorkSession] = None
        self.sessions: List[WorkSession] = []
        self.search_query = ""
        self.show_all_apps = False
        self.showing_why = False

        self._build_ui()
        self._refresh_timeline()
        self.collector.start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 1. Header Frame
        header = tk.Frame(self, bg="#ffffff", bd=1, relief="solid")
        header.pack(fill="x", padx=16, pady=(14, 6))

        inner_header = tk.Frame(header, bg="#ffffff", padx=16, pady=10)
        inner_header.pack(fill="x")

        title_box = tk.Frame(inner_header, bg="#ffffff")
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text="Breadcrumb",
            font=("Segoe UI", 16, "bold"),
            bg="#ffffff",
            fg="#0f172a"
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="“Your computer remembers where your brain stopped.”",
            font=("Segoe UI", 9, "italic"),
            bg="#ffffff",
            fg="#475569"
        ).pack(anchor="w")

        # Privacy Status Badge (Clickable modal launcher)
        privacy_btn = tk.Button(
            inner_header,
            text="● Tracking locally",
            font=("Segoe UI", 8, "bold"),
            bg="#f0fdf4",
            fg="#166534",
            bd=1,
            relief="solid",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._show_privacy_dialog
        )
        privacy_btn.pack(side="right")

        # 2. Live Status Bar
        status_bar = tk.Frame(self, bg="#ffffff", bd=1, relief="solid", padx=14, pady=6)
        status_bar.pack(fill="x", padx=16, pady=4)

        self.status_indicator = tk.Label(
            status_bar,
            text="● TRACKING ACTIVE",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#16a34a"
        )
        self.status_indicator.pack(side="left", padx=(0, 12))

        self.current_app_label = tk.Label(
            status_bar,
            text="Current: Detecting active window...",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#334155"
        )
        self.current_app_label.pack(side="left", fill="x", expand=True)

        # 3. Controls Toolbar
        controls = tk.Frame(self, bg="#f8fafc")
        controls.pack(fill="x", padx=16, pady=4)

        self.pause_btn = tk.Button(
            controls,
            text="⏸ Pause Tracking",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#334155",
            bd=1,
            relief="solid",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._toggle_pause
        )
        self.pause_btn.pack(side="left", padx=(0, 8))

        clear_btn = tk.Button(
            controls,
            text="🗑 Clear History",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#b91c1c",
            bd=1,
            relief="solid",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._clear_history
        )
        clear_btn.pack(side="left", padx=(0, 8))

        ignored_btn = tk.Button(
            controls,
            text="⚙ Ignored Apps",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#334155",
            bd=1,
            relief="solid",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._show_ignored_apps_dialog
        )
        ignored_btn.pack(side="left", padx=(0, 8))

        self.demo_btn = tk.Button(
            controls,
            text="⚡ Load Demo Scenario",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#4338ca",
            bd=1,
            relief="solid",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._load_demo
        )
        self.demo_btn.pack(side="right")

        # 4. Central Prominent Action Button
        action_frame = tk.Frame(self, bg="#f8fafc")
        action_frame.pack(fill="x", padx=16, pady=6)

        self.analyze_btn = tk.Button(
            action_frame,
            text="What was I doing?",
            font=("Segoe UI", 12, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            bd=0,
            padx=20,
            pady=9,
            cursor="hand2",
            command=self._analyze_context
        )
        self.analyze_btn.pack(fill="x")

        # 5. Split Main Content Area (PanedWindow)
        content_pane = tk.PanedWindow(self, orient="horizontal", bg="#e2e8f0", sashwidth=4, bd=0)
        content_pane.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        # --- Left Panel: Recent Timeline with Search ---
        timeline_frame = tk.Frame(content_pane, bg="#ffffff", bd=1, relief="solid")
        content_pane.add(timeline_frame, minsize=320, width=370)

        timeline_header = tk.Frame(timeline_frame, bg="#f1f5f9", padx=12, pady=6, bd=0)
        timeline_header.pack(fill="x")

        tk.Label(
            timeline_header,
            text="RECENT TIMELINE",
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#475569"
        ).pack(side="left")

        self.timeline_count_label = tk.Label(
            timeline_header,
            text="0 steps",
            font=("Segoe UI", 8),
            bg="#f1f5f9",
            fg="#64748b"
        )
        self.timeline_count_label.pack(side="right")

        # Search Bar
        search_box = tk.Frame(timeline_frame, bg="#ffffff", padx=8, pady=4)
        search_box.pack(fill="x")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        search_entry = tk.Entry(
            search_box,
            textvariable=self.search_var,
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#1e293b",
            bd=1,
            relief="solid"
        )
        search_entry.pack(fill="x", padx=2, pady=2)
        search_entry.insert(0, "")

        # Timeline listbox
        timeline_scroll = tk.Scrollbar(timeline_frame)
        timeline_scroll.pack(side="right", fill="y")

        self.timeline_list = tk.Listbox(
            timeline_frame,
            font=("Consolas", 9),
            bg="#ffffff",
            fg="#1e293b",
            selectbackground="#e0e7ff",
            selectforeground="#1e1b4b",
            bd=0,
            highlightthickness=0,
            yscrollcommand=timeline_scroll.set
        )
        self.timeline_list.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        timeline_scroll.config(command=self.timeline_list.yview)

        # --- Right Panel: Resume Context (Cards) ---
        context_container = tk.Frame(content_pane, bg="#ffffff", bd=1, relief="solid")
        content_pane.add(context_container, minsize=400, width=540)

        # Header with compact Copy Button at top-right
        context_header = tk.Frame(context_container, bg="#f8fafc", padx=14, pady=8, bd=1, relief="solid")
        context_header.pack(fill="x")

        tk.Label(
            context_header,
            text="RESUME CONTEXT",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#475569"
        ).pack(side="left")

        self.copy_btn = tk.Button(
            context_header,
            text="📋 Copy context",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#334155",
            bd=1,
            relief="solid",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._copy_context
        )
        self.copy_btn.pack(side="right")

        # Scrollable area
        self.scroll_frame = ScrollableFrame(context_container, bg="#ffffff")
        self.scroll_frame.pack(fill="both", expand=True)
        self.context_body = self.scroll_frame.scrollable_content

        self._render_initial_state()

    # -------------------------------------------------------------
    # RENDERERS: Cards and Structured Context
    # -------------------------------------------------------------

    def _clear_context_body(self):
        for widget in self.context_body.winfo_children():
            widget.destroy()

    def _render_initial_state(self):
        self._clear_context_body()
        card = tk.Frame(self.context_body, bg="#f8fafc", bd=1, relief="solid", padx=20, pady=24)
        card.pack(fill="x", padx=16, pady=20)

        tk.Label(
            card,
            text="Ready to reconstruct your context",
            font=("Segoe UI", 12, "bold"),
            bg="#f8fafc",
            fg="#0f172a"
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            card,
            text="Click “What was I doing?” above to analyze your recent work trail.\n\n"
                 "Breadcrumb partitions your events into discrete Work Sessions, calculates time spent, "
                 "and separates observed system facts from heuristic inferences.",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#475569",
            justify="left",
            wraplength=440
        ).pack(anchor="w", pady=(0, 14))

        tk.Label(
            card,
            text="⚡ Tip: Click “Load Demo Scenario” to test multi-session context recovery immediately.",
            font=("Segoe UI", 8, "italic"),
            bg="#f8fafc",
            fg="#64748b"
        ).pack(anchor="w")

    def _render_empty_state(self):
        self._clear_context_body()
        card = tk.Frame(self.context_body, bg="#f8fafc", bd=1, relief="solid", padx=20, pady=24)
        card.pack(fill="x", padx=16, pady=20)

        tk.Label(
            card,
            text="No recent activity recorded yet",
            font=("Segoe UI", 12, "bold"),
            bg="#f8fafc",
            fg="#0f172a"
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            card,
            text="Start working across applications and Breadcrumb will record your trail automatically.\n"
                 "All data stays 100% private on your machine.",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#475569",
            justify="left"
        ).pack(anchor="w")

    def _render_structured_context(self, ctx: ResumeContext):
        self._clear_context_body()

        container = tk.Frame(self.context_body, bg="#ffffff", padx=16, pady=12)
        container.pack(fill="both", expand=True)

        # ---------------------------------------------------------
        # 1. HERO: PICK UP WHERE YOU LEFT OFF
        # ---------------------------------------------------------
        hero_card = tk.Frame(container, bg="#ffffff", bd=1, relief="solid", padx=16, pady=14)
        hero_card.pack(fill="x", pady=(0, 12))

        hero_top = tk.Frame(hero_card, bg="#ffffff")
        hero_top.pack(fill="x")

        tk.Label(
            hero_top,
            text="PICK UP WHERE YOU LEFT OFF",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(side="left")

        # Session duration pill
        dur_pill = tk.Label(
            hero_top,
            text=f"{ctx.session_duration} session",
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#334155",
            bd=1,
            relief="solid",
            padx=8,
            pady=1
        )
        dur_pill.pack(side="right")

        # Project / Application line
        proj_icon = get_app_icon(ctx.last_app or "")
        proj_name = ctx.primary_project or "Current Workspace"
        headline_frame = tk.Frame(hero_card, bg="#ffffff")
        headline_frame.pack(fill="x", pady=(6, 2))

        tk.Label(
            headline_frame,
            text=f"{proj_icon}  {proj_name}",
            font=("Segoe UI", 15, "bold"),
            bg="#ffffff",
            fg="#0f172a",
            wraplength=460,
            justify="left"
        ).pack(anchor="w")

        # Context headline
        clean_headline = ctx.headline
        tk.Label(
            hero_card,
            text=clean_headline,
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#334155"
        ).pack(anchor="w", pady=(0, 4))

        # Last active metadata
        last_entity = ctx.last_entity or "recent files"
        last_app = ctx.last_app or "editor"
        last_time = ctx.last_time or "now"
        tk.Label(
            hero_card,
            text=f"Last active: {last_entity} · {last_app} · {last_time}",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#64748b"
        ).pack(anchor="w", pady=(0, 10))

        # Primary Action Button: Pick up where I left off
        self.pickup_btn = tk.Button(
            hero_card,
            text="➜  Pick up where I left off",
            font=("Segoe UI", 10, "bold"),
            bg="#0f172a",
            fg="#ffffff",
            activebackground="#1e293b",
            activeforeground="#ffffff",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            command=lambda: self._on_pickup_clicked(ctx)
        )
        self.pickup_btn.pack(anchor="w")

        # ---------------------------------------------------------
        # 2. SESSION STORY
        # ---------------------------------------------------------
        tk.Label(
            container,
            text="SESSION",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(anchor="w", pady=(2, 4))

        session_card = tk.Frame(container, bg="#f8fafc", bd=1, relief="solid", padx=14, pady=12)
        session_card.pack(fill="x", pady=(0, 12))

        # Time span row
        span_row = tk.Frame(session_card, bg="#f8fafc")
        span_row.pack(fill="x")

        tk.Label(
            span_row,
            text=ctx.session_time_span,
            font=("Segoe UI", 10, "bold"),
            bg="#f8fafc",
            fg="#0f172a"
        ).pack(side="left")

        tk.Label(
            span_row,
            text=f"{ctx.session_duration}",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#64748b"
        ).pack(side="right")

        # Flow sequence
        flow_frame = tk.Frame(session_card, bg="#f8fafc")
        flow_frame.pack(fill="x", pady=(6, 10))

        tk.Label(
            flow_frame,
            text=ctx.flow_text,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#2563eb",
            wraplength=460,
            justify="left"
        ).pack(anchor="w")

        # Approximate Time Spent per Application
        if ctx.app_durations:
            time_box = tk.Frame(session_card, bg="#f8fafc")
            time_box.pack(fill="x", pady=(2, 0))

            max_mins = max(mins for _, mins, _, _ in ctx.app_durations) if ctx.app_durations else 1

            for app_name, mins, mins_lbl, ev_cnt in ctx.app_durations[:5]:
                row = tk.Frame(time_box, bg="#f8fafc", pady=2)
                row.pack(fill="x")

                icon = get_app_icon(app_name)
                tk.Label(
                    row,
                    text=f"{icon} {truncate_text(app_name, 16)}",
                    font=("Segoe UI", 9),
                    bg="#f8fafc",
                    fg="#1e293b",
                    width=16,
                    anchor="w"
                ).pack(side="left")

                tk.Label(
                    row,
                    text=mins_lbl,
                    font=("Segoe UI", 8, "bold"),
                    bg="#f8fafc",
                    fg="#475569",
                    width=5,
                    anchor="w"
                ).pack(side="left", padx=(4, 6))

                bar_canvas = tk.Canvas(row, width=110, height=7, bg="#e2e8f0", bd=0, highlightthickness=0)
                bar_canvas.pack(side="left", padx=4)
                bar_w = max(4, int(110 * (mins / max_mins)))
                bar_canvas.create_rectangle(0, 0, bar_w, 7, fill="#475569", outline="")

                tk.Label(
                    row,
                    text=f"{ev_cnt} events",
                    font=("Segoe UI", 8),
                    bg="#f8fafc",
                    fg="#94a3b8",
                    anchor="e"
                ).pack(side="right")

            tk.Label(
                session_card,
                text="Approx. active time",
                font=("Segoe UI", 8, "italic"),
                bg="#f8fafc",
                fg="#94a3b8"
            ).pack(anchor="w", pady=(6, 0))

        # ---------------------------------------------------------
        # 3. OBSERVED (System Recorded)
        # ---------------------------------------------------------
        obs_header = tk.Frame(container, bg="#ffffff")
        obs_header.pack(fill="x", pady=(2, 4))

        tk.Label(
            obs_header,
            text="OBSERVED",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(side="left")

        tk.Label(
            obs_header,
            text="SYSTEM RECORDED",
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            bd=1,
            relief="solid",
            padx=6,
            pady=1
        ).pack(side="right")

        obs_card = tk.Frame(container, bg="#ffffff", bd=1, relief="solid", padx=14, pady=10)
        obs_card.pack(fill="x", pady=(0, 12))

        for obs in ctx.observed_facts[:4]:
            r = tk.Frame(obs_card, bg="#ffffff", pady=2)
            r.pack(fill="x")
            tk.Label(r, text="✓", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#16a34a").pack(side="left", anchor="n", padx=(0, 6))
            tk.Label(r, text=obs.lstrip("✓*• "), font=("Segoe UI", 9), bg="#ffffff", fg="#1e293b", wraplength=440, justify="left").pack(side="left", fill="x", expand=True)

        # ---------------------------------------------------------
        # 4. INFERRED CONTEXT (With [Why?] Explainability)
        # ---------------------------------------------------------
        inf_header = tk.Frame(container, bg="#ffffff")
        inf_header.pack(fill="x", pady=(2, 4))

        tk.Label(
            inf_header,
            text="INFERRED",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#64748b"
        ).pack(side="left")

        tk.Label(
            inf_header,
            text="AI INTERPRETATION",
            font=("Segoe UI", 7, "bold"),
            bg="#fef3c7",
            fg="#92400e",
            bd=1,
            relief="solid",
            padx=6,
            pady=1
        ).pack(side="right")

        inf_card = tk.Frame(container, bg="#ffffff", bd=1, relief="solid", padx=14, pady=10)
        inf_card.pack(fill="x", pady=(0, 12))

        primary_inf = ctx.inferences[0] if ctx.inferences else "Active development session."
        inf_top = tk.Frame(inf_card, bg="#ffffff")
        inf_top.pack(fill="x")

        tk.Label(
            inf_top,
            text=f"“{primary_inf}”",
            font=("Segoe UI", 9, "italic"),
            bg="#ffffff",
            fg="#1e293b",
            wraplength=380,
            justify="left"
        ).pack(side="left", fill="x", expand=True)

        # [ Why? ] Explainability Button
        self.why_btn = tk.Button(
            inf_top,
            text="Why?",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#2563eb",
            bd=1,
            relief="solid",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self._toggle_why
        )
        self.why_btn.pack(side="right", padx=(8, 0))

        # Expandable "Why?" evidence card
        self.why_frame = tk.Frame(inf_card, bg="#f8fafc", bd=1, relief="solid", padx=12, pady=8)
        # Hidden by default until clicked
        tk.Label(
            self.why_frame,
            text="WHY THIS INFERENCE?",
            font=("Segoe UI", 8, "bold"),
            bg="#f8fafc",
            fg="#475569"
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            self.why_frame,
            text="Breadcrumb detected the following evidence:",
            font=("Segoe UI", 8, "italic"),
            bg="#f8fafc",
            fg="#64748b"
        ).pack(anchor="w", pady=(0, 4))

        reasons = []
        if ctx.inferences_with_reasons:
            reasons = ctx.inferences_with_reasons[0].get("reasons", [])
        if not reasons:
            reasons = [f"{last_entity} was active in {last_app}", f"{last_app} remained the final active application"]

        for r in reasons:
            rf = tk.Frame(self.why_frame, bg="#f8fafc", pady=1)
            rf.pack(fill="x")
            tk.Label(rf, text="✓", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#16a34a").pack(side="left", padx=(0, 4))
            tk.Label(rf, text=r, font=("Segoe UI", 8), bg="#f8fafc", fg="#334155").pack(side="left")

        # ---------------------------------------------------------
        # 5. SUGGESTED NEXT STEP
        # ---------------------------------------------------------
        if ctx.suggested_next_step:
            next_card = tk.Frame(container, bg="#f0fdf4", bd=1, relief="solid", padx=14, pady=10)
            next_card.pack(fill="x", pady=(0, 10))

            tk.Label(
                next_card,
                text="SUGGESTED NEXT STEP",
                font=("Segoe UI", 8, "bold"),
                bg="#f0fdf4",
                fg="#15803d"
            ).pack(anchor="w")

            tk.Label(
                next_card,
                text=f"★  {ctx.suggested_next_step}",
                font=("Segoe UI", 9, "bold"),
                bg="#f0fdf4",
                fg="#14532d",
                wraplength=440,
                justify="left"
            ).pack(anchor="w", pady=(2, 0))

        # Footer meta label
        tk.Label(
            container,
            text=f"Generated via {ctx.engine_used} • Local Storage Only",
            font=("Segoe UI", 8, "italic"),
            bg="#ffffff",
            fg="#94a3b8"
        ).pack(anchor="w", pady=(4, 0))

    def _toggle_why(self):
        """Toggles the 'Why?' inference evidence card."""
        self.showing_why = not self.showing_why
        if self.showing_why:
            self.why_frame.pack(fill="x", pady=(8, 0))
            self.why_btn.config(text="Close", fg="#64748b")
        else:
            self.why_frame.pack_forget()
            self.why_btn.config(text="Why?", fg="#2563eb")

    def _on_pickup_clicked(self, ctx: ResumeContext):
        """Handles the primary 'Pick up where I left off' button."""
        target_app = ctx.last_app or ""
        target_entity = ctx.last_entity or ""
        success = try_focus_window(target_app, target_entity)

        if success:
            self.pickup_btn.config(text=f"✓ Focused {target_app}!", bg="#15803d")
        else:
            self.pickup_btn.config(text=f"✓ Resumed: {truncate_text(target_entity or target_app, 26)}", bg="#15803d")

        self.after(2000, lambda: self.pickup_btn.config(text="➜  Pick up where I left off", bg="#0f172a"))

    # -------------------------------------------------------------
    # TIMELINE & SEARCH
    # -------------------------------------------------------------

    def _on_search_change(self, *args):
        """Filters the timeline list when search input changes."""
        self.search_query = self.search_var.get()
        self._refresh_timeline()

    def _on_live_event(self, event_data: Dict[str, Any]):
        def update():
            app = event_data.get("app_name", "Unknown")
            title = event_data.get("window_title", "")
            self.current_app_label.config(text=f"Current: {app} — {truncate_text(title, 55)}")
            self._refresh_timeline()
        self.after(0, update)

    def _refresh_timeline(self):
        raw_events = self.storage.get_recent_events(limit=config.MAX_TIMELINE_DISPLAY_ITEMS)
        ignored = config.get_ignored_applications()

        # Sessionize
        self.sessions = TimelineAggregator.group_into_sessions(
            raw_events,
            inactivity_threshold_minutes=config.SESSION_INACTIVITY_THRESHOLD_MINUTES,
            ignored_apps=ignored
        )
        self.latest_session = self.sessions[-1] if self.sessions else None

        # Filter events by search query if typed
        filtered_events = raw_events
        if self.search_query:
            filtered_events = TimelineAggregator.filter_events(raw_events, self.search_query)

        self.timeline_list.delete(0, tk.END)

        if not self.sessions:
            self.timeline_count_label.config(text="0 sessions")
            return

        # Render grouped by session (latest sessions on top or chronological)
        total_items = 0
        for s in reversed(self.sessions):
            # Session separator header
            header_str = f"── Session {s.session_id}: {s.time_span_label} ({s.duration_minutes}m) ──"
            self.timeline_list.insert(tk.END, header_str)

            session_events = [e for e in s.events if not self.search_query or e in filtered_events]
            for item in session_events:
                time_str = item["start_time_label"]
                app_str = item["app_name"]
                desc_str = item["description"]
                line = f"  {time_str}  {app_str.ljust(9)} — {desc_str}"
                self.timeline_list.insert(tk.END, line)
                total_items += 1

            self.timeline_list.insert(tk.END, "")  # blank spacer

        self.timeline_count_label.config(text=f"{len(self.sessions)} sessions · {total_items} steps")

    def _analyze_context(self):
        """Analyzes recent timeline and latest session."""
        raw_events = self.storage.get_recent_events(limit=config.MAX_TIMELINE_DISPLAY_ITEMS)
        ignored = config.get_ignored_applications()

        self.sessions = TimelineAggregator.group_into_sessions(
            raw_events,
            inactivity_threshold_minutes=config.SESSION_INACTIVITY_THRESHOLD_MINUTES,
            ignored_apps=ignored
        )

        if not self.sessions:
            self._render_empty_state()
            return

        self.latest_session = self.sessions[-1]
        self.current_context = ContextSummarizer.generate_context(
            self.latest_session.events,
            session=self.latest_session
        )
        self._render_structured_context(self.current_context)

    def _copy_context(self):
        """Copies structured context to clipboard with a brief confirmation."""
        if not self.current_context:
            return

        text = self.current_context.to_text()
        self.clipboard_clear()
        self.clipboard_append(text)

        self.copy_btn.config(text="✓ Copied", fg="#15803d")
        self.after(1500, lambda: self.copy_btn.config(text="📋 Copy context", fg="#334155"))

    def _toggle_pause(self):
        if self.collector.is_paused():
            self.collector.resume()
            self.pause_btn.config(text="⏸ Pause Tracking")
            self.status_indicator.config(text="● TRACKING ACTIVE", fg="#16a34a")
        else:
            self.collector.pause()
            self.pause_btn.config(text="▶ Resume Tracking")
            self.status_indicator.config(text="⏸ TRACKING PAUSED", fg="#ca8a04")

    def _clear_history(self):
        if messagebox.askyesno("Clear History", "Permanently clear all recorded local activity history?"):
            self.storage.clear_all()
            self.timeline_list.delete(0, tk.END)
            self.timeline_count_label.config(text="0 sessions")
            self._render_empty_state()
            self.current_context = None

    def _load_demo(self):
        self.collector.pause()
        self.pause_btn.config(text="▶ Resume Tracking")
        self.status_indicator.config(text="⚡ MULTI-SESSION DEMO LOADED", fg="#4338ca")

        load_demo_events(self.storage)
        self._refresh_timeline()
        self._analyze_context()

    # -------------------------------------------------------------
    # DIALOGS: Privacy & Ignored Applications
    # -------------------------------------------------------------

    def _show_privacy_dialog(self):
        """Displays privacy guarantees and status dialog."""
        win = tk.Toplevel(self)
        win.title("Privacy Status & Controls")
        win.geometry("420x340")
        win.resizable(False, False)
        win.configure(bg="#ffffff", padx=20, pady=20)
        win.transient(self)
        win.grab_set()

        tk.Label(
            win,
            text="PRIVACY STATUS",
            font=("Segoe UI", 12, "bold"),
            bg="#ffffff",
            fg="#0f172a"
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            win,
            text="Your digital activity stays strictly on this machine.",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#475569"
        ).pack(anchor="w", pady=(0, 14))

        guarantees = [
            "Activity is stored 100% locally in SQLite",
            "No screenshots or screen recordings",
            "No keystroke logging or clipboard capture",
            "No cloud servers, accounts, or telemetry upload"
        ]

        for g in guarantees:
            f = tk.Frame(win, bg="#ffffff", pady=2)
            f.pack(fill="x")
            tk.Label(f, text="✓", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#16a34a").pack(side="left", padx=(0, 8))
            tk.Label(f, text=g, font=("Segoe UI", 9), bg="#ffffff", fg="#1e293b").pack(side="left")

        # Divider
        tk.Frame(win, bg="#e2e8f0", height=1).pack(fill="x", pady=14)

        # Controls
        ctrl_frame = tk.Frame(win, bg="#ffffff")
        ctrl_frame.pack(fill="x")

        status_text = "Tracking: Active" if not self.collector.is_paused() else "Tracking: Paused"
        tk.Label(ctrl_frame, text=status_text, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#0f172a").pack(side="left")

        tk.Button(
            win,
            text="Close",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#334155",
            bd=1,
            relief="solid",
            padx=12,
            pady=4,
            cursor="hand2",
            command=win.destroy
        ).pack(side="right", pady=(10, 0))

    def _show_ignored_apps_dialog(self):
        """Displays dialog to manage ignored applications."""
        win = tk.Toplevel(self)
        win.title("Ignored Applications")
        win.geometry("420x400")
        win.resizable(False, False)
        win.configure(bg="#ffffff", padx=20, pady=20)
        win.transient(self)
        win.grab_set()

        tk.Label(
            win,
            text="IGNORED APPLICATIONS",
            font=("Segoe UI", 12, "bold"),
            bg="#ffffff",
            fg="#0f172a"
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            win,
            text="Excluded from session summaries, durations, and inferences:",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#475569"
        ).pack(anchor="w", pady=(0, 10))

        lb_frame = tk.Frame(win, bg="#ffffff")
        lb_frame.pack(fill="both", expand=True)

        lb = tk.Listbox(
            lb_frame,
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#1e293b",
            bd=1,
            relief="solid",
            height=7
        )
        lb.pack(fill="both", expand=True)

        current_ignored = config.get_ignored_applications()
        for app in current_ignored:
            lb.insert(tk.END, app)

        def remove_selected():
            sel = lb.curselection()
            if not sel:
                return
            idx = sel[0]
            val = lb.get(idx)
            current_ignored.remove(val)
            config.save_ignored_applications(current_ignored)
            lb.delete(idx)
            self._refresh_timeline()

        btn_row = tk.Frame(win, bg="#ffffff", pady=8)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row,
            text="Remove Selected",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#b91c1c",
            bd=1,
            relief="solid",
            padx=8,
            pady=3,
            cursor="hand2",
            command=remove_selected
        ).pack(side="left")

        # Add application section
        add_frame = tk.Frame(win, bg="#ffffff", pady=6)
        add_frame.pack(fill="x")

        add_entry = tk.Entry(add_frame, font=("Segoe UI", 9), bg="#f8fafc", fg="#1e293b", bd=1, relief="solid")
        add_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def add_app():
            new_app = add_entry.get().strip()
            if new_app and new_app not in current_ignored:
                current_ignored.append(new_app)
                config.save_ignored_applications(current_ignored)
                lb.insert(tk.END, new_app)
                add_entry.delete(0, tk.END)
                self._refresh_timeline()

        tk.Button(
            add_frame,
            text="+ Add App",
            font=("Segoe UI", 8, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=add_app
        ).pack(side="right")

    def _on_close(self):
        self.collector.stop()
        self.destroy()

def start_gui():
    app = BreadcrumbApp()
    app.mainloop()

if __name__ == "__main__":
    start_gui()
