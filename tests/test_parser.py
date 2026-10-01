"""Unit tests for ActivityParser."""
import unittest
from breadcrumb.parser import ActivityParser

class TestActivityParser(unittest.TestCase):
    def test_privacy_sanitization(self):
        """Ensures titles with sensitive terms are automatically masked."""
        sensitive_cases = [
            ("Bitwarden - Password Manager", "chrome.exe"),
            ("1Password - Vault", "1password.exe"),
            ("Account Login - Enter Password", "chrome.exe"),
            ("Personal Banking - Chase", "msedge.exe"),
            ("Incognito Window", "chrome.exe"),
        ]
        for title, proc in sensitive_cases:
            parsed = ActivityParser.parse_activity(title, proc)
            self.assertTrue(parsed["is_sensitive"])
            self.assertEqual(parsed["app_name"], "Protected Application")
            self.assertIn("masked", parsed["window_title"].lower())

    def test_vscode_parsing(self):
        """Tests file and project extraction from VS Code window titles."""
        title = "auth_service.py - agentdesk - Visual Studio Code"
        parsed = ActivityParser.parse_activity(title, "Code.exe")
        self.assertFalse(parsed["is_sensitive"])
        self.assertEqual(parsed["app_name"], "VS Code")
        self.assertEqual(parsed["entity"], "auth_service.py")
        self.assertEqual(parsed["project"], "agentdesk")
        self.assertEqual(parsed["category"], "editor")

    def test_browser_parsing(self):
        """Tests GitHub and documentation identification in browser titles."""
        title = "Issue #42: Session token expired · GitHub - Google Chrome"
        parsed = ActivityParser.parse_activity(title, "chrome.exe")
        self.assertFalse(parsed["is_sensitive"])
        self.assertEqual(parsed["app_name"], "Chrome")
        self.assertEqual(parsed["project"], "GitHub")
        self.assertIn("Issue #42", parsed["clean_title"])
        self.assertEqual(parsed["category"], "browser")

    def test_terminal_parsing(self):
        """Tests terminal command extraction."""
        title = "Windows PowerShell - pytest tests/test_auth.py"
        parsed = ActivityParser.parse_activity(title, "powershell.exe")
        self.assertFalse(parsed["is_sensitive"])
        self.assertEqual(parsed["app_name"], "Terminal")
        self.assertEqual(parsed["entity"], "pytest tests/test_auth.py")
        self.assertEqual(parsed["category"], "terminal")

if __name__ == "__main__":
    unittest.main()
