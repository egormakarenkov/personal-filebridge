import json
import tempfile
import unittest
import uuid
from pathlib import Path

from filebridge.dashboard import load_dashboard_data


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.recovery = self.root / "recovery"
        self.recovery.mkdir()
        self.allowed = self.root / "allowed"
        self.allowed.mkdir()

    def test_missing_configuration_is_reported_without_creating_files(self):
        result = load_dashboard_data(self.state, self.recovery)
        self.assertEqual(result["status"], "Setup required")
        self.assertEqual(result["allowed_roots"], [])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_recent_audit_and_recovery_are_filtered(self):
        (self.state / "config.json").write_text(json.dumps({"allowed_roots": [str(self.allowed)]}), encoding="utf-8")
        valid_id = str(uuid.uuid4())
        excluded_id = str(uuid.uuid4())
        for recovery_id, original in ((valid_id, self.allowed / "gone.txt"), (excluded_id, self.root / "outside.txt")):
            (self.recovery / recovery_id).write_text("saved", encoding="utf-8")
            (self.recovery / f"{recovery_id}.json").write_text(json.dumps({
                "recovery_id": recovery_id, "original_path": str(original), "operation": "move",
            }), encoding="utf-8")
        (self.state / "audit.jsonl").write_text(
            '{"action":"write","result":"ok","path":"sample.txt","time_utc":1}\ninvalid\n', encoding="utf-8",
        )
        result = load_dashboard_data(self.state, self.recovery)
        self.assertEqual(result["status"], "Configured")
        self.assertEqual(result["allowed_roots"], [str(self.allowed)])
        self.assertEqual(len(result["audit"]), 1)
        self.assertEqual([item["recovery_id"] for item in result["recovery"]], [valid_id])


if __name__ == "__main__":
    unittest.main()
