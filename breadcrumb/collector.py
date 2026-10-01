"""Windows Foreground Window & Activity Collector.

Captures active window title and process name in a lightweight background thread.
Enforces local-only storage, debouncing, and tracking pause/resume controls.
"""
import sys
import time
import threading
import logging
from typing import Optional, Callable, Dict, Any, Tuple
from datetime import datetime

from breadcrumb.parser import ActivityParser
from breadcrumb.storage import EventStore
import config

logger = logging.getLogger(__name__)

# Windows ctypes imports if on Windows
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes

class ActivityCollector:
    def __init__(
        self,
        storage: EventStore,
        poll_interval: float = config.POLL_INTERVAL_SECONDS,
        on_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.storage = storage
        self.poll_interval = poll_interval
        self.on_event_callback = on_event_callback

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None

        self._last_title: Optional[str] = None
        self._last_app: Optional[str] = None
        self._last_event_time: Optional[float] = None
        self._last_inserted_id: Optional[int] = None

    def start(self):
        """Starts the background tracking thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ActivityCollectorThread")
        self._thread.start()
        logger.info("ActivityCollector started.")

    def stop(self):
        """Stops the tracking thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("ActivityCollector stopped.")

    def pause(self):
        """Pauses tracking without stopping the thread."""
        self._paused = True
        logger.info("Activity tracking paused.")

    def resume(self):
        """Resumes tracking."""
        self._paused = False
        self._last_title = None  # Force immediate check on resume
        logger.info("Activity tracking resumed.")

    def is_paused(self) -> bool:
        return self._paused

    def is_running(self) -> bool:
        return self._running

    def get_current_foreground_window(self) -> Tuple[Optional[str], Optional[str]]:
        """Queries the current active window title and process name from Windows."""
        if not IS_WINDOWS:
            return "Test Window", "test.exe"

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return None, None

            # Get Window Title
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                title = ""
            else:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value

            # Get Process Name
            pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            proc_name = None
            if pid.value:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h_process = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
                )
                if h_process:
                    import os
                    exe_buf = ctypes.create_unicode_buffer(1024)
                    size = ctypes.wintypes.DWORD(1024)
                    if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                        h_process, 0, exe_buf, ctypes.byref(size)
                    ):
                        proc_name = os.path.basename(exe_buf.value)
                    ctypes.windll.kernel32.CloseHandle(h_process)

            return title, proc_name
        except Exception as e:
            logger.debug(f"Error reading foreground window: {e}")
            return None, None

    def _run_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                if not self._paused:
                    self._check_and_record()
            except Exception as e:
                logger.error(f"Error in activity collector loop: {e}")

            time.sleep(self.poll_interval)

    def _check_and_record(self):
        """Checks current window and persists changes to storage."""
        raw_title, proc_name = self.get_current_foreground_window()
        
        # Ignore empty/hidden desktop transitions
        if not raw_title and not proc_name:
            return

        # Ignore Breadcrumb's own window so inspecting Breadcrumb doesn't overwrite real work context
        if raw_title and raw_title.startswith("Breadcrumb"):
            return

        now = time.time()
        
        # Debounce: if same window title and app, update duration on recent record
        if raw_title == self._last_title and self._last_event_time is not None:
            # Heartbeat: don't insert duplicate record every 2s
            return

        # New window or app detected
        parsed = ActivityParser.parse_activity(raw_title, proc_name)

        # Ignore configured applications (e.g. Spotify, WhatsApp, Netflix)
        ignored = config.get_ignored_applications()
        if any(ign.lower() == parsed["app_name"].lower() for ign in ignored):
            self._last_title = raw_title
            return
        
        # Calculate duration of previous window
        duration = 0.0
        if self._last_event_time:
            duration = max(0.0, round(now - self._last_event_time, 1))

        iso_time = datetime.now().isoformat(timespec="seconds")
        event_id = self.storage.insert_event(
            app_name=parsed["app_name"],
            window_title=parsed["clean_title"],
            process_name=proc_name,
            entity=parsed["entity"],
            project=parsed["project"],
            timestamp=iso_time,
            duration_seconds=duration,
        )

        self._last_title = raw_title
        self._last_app = parsed["app_name"]
        self._last_event_time = now
        self._last_inserted_id = event_id

        event_payload = {
            "id": event_id,
            "timestamp": iso_time,
            "app_name": parsed["app_name"],
            "window_title": parsed["clean_title"],
            "entity": parsed["entity"],
            "project": parsed["project"],
            "category": parsed["category"],
            "is_sensitive": parsed["is_sensitive"],
        }

        if self.on_event_callback:
            try:
                self.on_event_callback(event_payload)
            except Exception as cb_err:
                logger.debug(f"Event callback exception: {cb_err}")
