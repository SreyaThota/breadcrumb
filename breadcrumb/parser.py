"""Window title parsing, sanitization, and entity extraction.

Extracts meaningful metadata (file names, projects, web topics, commands)
while enforcing strict privacy filters against sensitive keywords.
"""
import re
import os
from typing import Dict, Any, Optional, Tuple
from config import SENSITIVE_KEYWORDS

# Process executable to friendly display name mapping
PROCESS_MAP = {
    "code.exe": "VS Code",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "windowsterminal.exe": "Terminal",
    "powershell.exe": "Terminal",
    "cmd.exe": "Terminal",
    "bash.exe": "Terminal",
    "wsl.exe": "Terminal",
    "notepad.exe": "Notepad",
    "notepad++.exe": "Notepad++",
    "sublime_text.exe": "Sublime Text",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "devenv.exe": "Visual Studio",
    "slack.exe": "Slack",
    "discord.exe": "Discord",
    "teams.exe": "Teams",
    "acrobat.exe": "Acrobat Reader",
    "acrord32.exe": "Acrobat Reader",
    "explorer.exe": "File Explorer",
    "postman.exe": "Postman",
    "spotify.exe": "Spotify",
    "applicationframehost.exe": "Windows Settings",
    "shellexperiencehost.exe": "Windows Shell",
}

class ActivityParser:
    @staticmethod
    def is_sensitive(title: str, process_name: Optional[str] = None) -> bool:
        """Checks if title or process matches any sensitive keyword."""
        combined = f"{title.lower()} {process_name.lower() if process_name else ''}"
        return any(keyword in combined for keyword in SENSITIVE_KEYWORDS)

    @classmethod
    def resolve_app_name(cls, process_name: Optional[str], raw_title: str) -> str:
        """Determines friendly application name from process executable or title."""
        if process_name:
            proc_key = process_name.strip().lower()
            if proc_key in PROCESS_MAP:
                return PROCESS_MAP[proc_key]
        
        # Fallback to inspecting window title markers
        lower_title = raw_title.lower()
        if "visual studio code" in lower_title or "vs code" in lower_title:
            return "VS Code"
        if "antigravity" in lower_title:
            return "Antigravity IDE"
        if "google chrome" in lower_title:
            return "Chrome"
        if "microsoft edge" in lower_title:
            return "Edge"
        if "firefox" in lower_title:
            return "Firefox"
        if "powershell" in lower_title or "command prompt" in lower_title or "terminal" in lower_title:
            return "Terminal"
        if "slack" in lower_title:
            return "Slack"
        
        if process_name:
            # Clean generic process (e.g., 'myapp.exe' -> 'Myapp')
            base = os.path.splitext(process_name)[0]
            return base.capitalize()

        return "Desktop"

    @classmethod
    def parse_activity(cls, raw_title: Optional[str], process_name: Optional[str] = None) -> Dict[str, Any]:
        """Parses raw window title and process into structured activity metadata."""
        if not raw_title or not raw_title.strip():
            raw_title = "Desktop / Idle"

        raw_title = raw_title.strip()

        # Privacy check: mask title if sensitive keywords found
        if cls.is_sensitive(raw_title, process_name):
            return {
                "app_name": "Protected Application",
                "window_title": "[Activity masked for privacy]",
                "clean_title": "[Protected]",
                "entity": None,
                "project": None,
                "category": "protected",
                "is_sensitive": True,
            }

        app_name = cls.resolve_app_name(process_name, raw_title)
        entity, project, category, clean_title = cls._extract_entities(app_name, raw_title)

        return {
            "app_name": app_name,
            "window_title": raw_title,
            "clean_title": clean_title,
            "entity": entity,
            "project": project,
            "category": category,
            "is_sensitive": False,
        }

    @classmethod
    def _extract_entities(
        cls, app_name: str, title: str
    ) -> Tuple[Optional[str], Optional[str], str, str]:
        """Extracts specific entity (filename, webpage, command) and project from title."""
        entity: Optional[str] = None
        project: Optional[str] = None
        category = "general"
        clean_title = title

        # Strip standard application suffixes from title
        clean_display = re.sub(
            r"\s*[-—·]\s*(Visual Studio Code|Antigravity IDE|Google Chrome|Microsoft​ Edge|Mozilla Firefox|Notepad).*$",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()

        if app_name in ("VS Code", "Antigravity IDE"):
            category = "editor"
            # Typical patterns:
            # - "● auth_service.py - agentdesk - Visual Studio Code"
            # - "auth_service.py - agentdesk - Visual Studio Code"
            # - "agentdesk - Visual Studio Code"
            # - "Welcome - Visual Studio Code"
            clean_display = clean_display.lstrip("●* ").strip()
            parts = [p.strip() for p in clean_display.split(" - ") if p.strip()]
            
            if len(parts) >= 2:
                entity = parts[0]
                project = parts[1]
                clean_title = f"{entity} ({project})"
            elif len(parts) == 1:
                part = parts[0]
                # If part is just the editor name, don't label it as a project
                if part.lower() in ("visual studio code", "vs code", "antigravity ide", "antigravity", "welcome"):
                    entity = None
                    project = None
                    clean_title = "Editor Workspace"
                elif "." in part and not part.startswith("."):
                    entity = part
                    clean_title = entity
                else:
                    project = part
                    clean_title = f"Project: {project}"

        elif app_name in ("Chrome", "Edge", "Firefox", "Brave"):
            category = "browser"
            # Examples:
            # - "Issue #42 - pytest failure · GitHub"
            # - "GitHub Actions documentation"
            # - "Stack Overflow - Python asyncio task"
            clean_title = clean_display
            
            # Identify high-level web service / topic
            if "github" in title.lower():
                project = "GitHub"
                entity = clean_display
            elif "gitlab" in title.lower():
                project = "GitLab"
                entity = clean_display
            elif "stack overflow" in title.lower():
                project = "Stack Overflow"
                entity = clean_display
            elif "docs" in title.lower() or "documentation" in title.lower():
                project = "Documentation"
                entity = clean_display
            else:
                entity = clean_display

        elif app_name == "Terminal":
            category = "terminal"
            # Examples:
            # - "Administrator: Windows PowerShell - pytest"
            # - "MINGW64:/c/project (main) - git status"
            # - "cmd - python run.py"
            # Extract trailing command after dash or colon if present
            m = re.search(r"[-—]\s*(.+)$", clean_display)
            if m:
                entity = m.group(1).strip()
                clean_title = f"Ran `{entity}`"
            else:
                clean_title = clean_display
                entity = clean_display

        elif app_name in ("Slack", "Discord", "Teams"):
            category = "communication"
            clean_title = clean_display
            entity = clean_display

        elif app_name == "File Explorer":
            category = "filesystem"
            clean_title = f"Folder: {clean_display}"
            entity = clean_display

        else:
            clean_title = clean_display
            entity = clean_display

        return entity, project, category, clean_title
