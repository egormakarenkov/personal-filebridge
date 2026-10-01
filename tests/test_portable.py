import sys
import unittest
from unittest.mock import patch

from filebridge.approval import _approval_command
from portable import main


class PortableEntrypointTests(unittest.TestCase):
    def test_approval_uses_same_executable_when_frozen(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", r"C:\Filebridge\PersonalFilebridge.exe"):
            self.assertEqual(_approval_command(60), [r"C:\Filebridge\PersonalFilebridge.exe", "--approval-dialog", "60"])

    def test_approval_uses_python_module_from_source(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(_approval_command(60), [sys.executable, "-m", "filebridge.approval", "60"])

    def test_portable_entrypoint_routes_dashboard_and_server(self):
        with patch.object(sys, "argv", ["PersonalFilebridge.exe", "--dashboard", "--check"]), patch("filebridge.dashboard.main") as dashboard:
            main()
            dashboard.assert_called_once()
            self.assertEqual(sys.argv[1:], ["--check"])
        with patch.object(sys, "argv", ["PersonalFilebridge.exe", "--transport", "init"]), patch("filebridge.server.main") as server:
            main()
            server.assert_called_once()


if __name__ == "__main__":
    unittest.main()
