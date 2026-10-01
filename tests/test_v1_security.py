import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filebridge.approval import _summary
from filebridge.core import FileBridge, FileBridgeError


class V1SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "allowed"
        self.data.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def bridge(self, *, roots=None, approver=None):
        return FileBridge(
            self.root / "state", self.root / "recovery",
            allowed_roots=roots, approver=approver,
        )

    def test_no_configured_roots_denies_all_file_access(self):
        target = self.data / "note.txt"
        target.write_text("private", encoding="utf-8")
        bridge = self.bridge(roots=[])
        with self.assertRaises(FileBridgeError):
            bridge.inspect_path(str(target))

    def test_access_outside_allowed_root_is_denied(self):
        target = self.outside / "note.txt"
        target.write_text("private", encoding="utf-8")
        bridge = self.bridge(roots=[self.data])
        with self.assertRaises(FileBridgeError):
            bridge.read_text(str(target))

    def test_relative_allowed_root_is_rejected(self):
        with self.assertRaises(FileBridgeError):
            self.bridge(roots=[Path(".")])

    def test_denied_approval_keeps_file_unchanged(self):
        target = self.data / "note.txt"
        target.write_text("before", encoding="utf-8")
        bridge = self.bridge(roots=[self.data], approver=lambda preview: False)
        read = bridge.read_text(str(target))
        op = bridge.prepare_write_text(str(target), "after", read["sha256"])
        with self.assertRaises(FileBridgeError):
            bridge.commit_write_text(op["operation_id"])
        self.assertEqual(target.read_text(encoding="utf-8"), "before")

    def test_write_approval_preview_can_be_rendered(self):
        target = self.data / "note.txt"
        target.write_text("before", encoding="utf-8")
        previews = []
        bridge = self.bridge(roots=[self.data], approver=lambda preview: previews.append(preview) or True)
        read = bridge.read_text(str(target))
        operation = bridge.prepare_write_text(str(target), "after", read["sha256"])
        bridge.commit_write_text(operation["operation_id"])
        summary = _summary(previews[0])
        self.assertIn(str(target), summary)
        self.assertIn("Replacement size: 5 bytes", summary)
        self.assertNotIn("Deletion:", summary)

    def test_delete_approval_summary_has_no_replacement_size(self):
        target = self.data / "note.txt"
        target.write_text("before", encoding="utf-8")
        previews = []
        bridge = self.bridge(roots=[self.data], approver=lambda preview: previews.append(preview) or True)
        operation = bridge.prepare_delete(str(target), permanent=False)
        bridge.commit_delete(operation["operation_id"])
        summary = _summary(previews[0])
        self.assertIn("Deletion: Recoverable", summary)
        self.assertNotIn("Replacement size", summary)

    def test_missing_approver_fails_closed(self):
        target = self.data / "note.txt"
        target.write_text("before", encoding="utf-8")
        bridge = self.bridge(roots=[self.data])
        op = bridge.prepare_delete(str(target), permanent=True)
        with self.assertRaises(FileBridgeError):
            bridge.commit_delete(op["operation_id"])
        self.assertTrue(target.exists())

    def test_same_size_same_timestamp_directory_change_is_detected(self):
        folder = self.data / "folder"
        folder.mkdir()
        target = folder / "item.txt"
        target.write_text("AAAA", encoding="utf-8")
        bridge = self.bridge(roots=[self.data], approver=lambda preview: True)
        op = bridge.prepare_delete(str(folder), permanent=True)
        stat = target.stat()
        target.write_text("BBBB", encoding="utf-8")
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaises(FileBridgeError):
            bridge.commit_delete(op["operation_id"])
        self.assertTrue(target.exists())

    def test_prepared_write_contents_are_not_saved_to_disk(self):
        target = self.data / "note.txt"
        bridge = self.bridge(roots=[self.data], approver=lambda preview: True)
        bridge.prepare_write_text(str(target), "unique staged secret", None)
        state_files = [p for p in (self.root / "state").rglob("*") if p.is_file()]
        self.assertEqual(state_files, [])

    def test_pending_operations_have_a_limit(self):
        bridge = self.bridge(roots=[self.data], approver=lambda preview: True)
        for index in range(bridge.MAX_PENDING_OPERATIONS):
            bridge.prepare_write_text(str(self.data / f"{index}.txt"), "x", None)
        with self.assertRaises(FileBridgeError):
            bridge.prepare_write_text(str(self.data / "extra.txt"), "x", None)

    def test_directory_preview_fails_when_walk_reports_an_error(self):
        folder = self.data / "folder"
        folder.mkdir()
        bridge = self.bridge(roots=[self.data], approver=lambda preview: True)

        def failing_walk(path, **kwargs):
            kwargs["onerror"](PermissionError("cannot inspect child"))
            return iter(())

        with patch("filebridge.core.os.walk", side_effect=failing_walk):
            with self.assertRaises(FileBridgeError):
                bridge.prepare_delete(str(folder), permanent=True)

    def test_recovery_listing_obeys_current_allowed_roots(self):
        target = self.data / "old.txt"
        target.write_text("old", encoding="utf-8")
        original = self.bridge(roots=[self.data], approver=lambda preview: True)
        operation = original.prepare_delete(str(target), permanent=False)
        original.commit_delete(operation["operation_id"])
        restricted = self.bridge(roots=[self.outside], approver=lambda preview: True)
        self.assertEqual(restricted.list_recovery()["items"], [])

    def test_restore_requires_local_owner_approval(self):
        target = self.data / "old.txt"
        target.write_text("old", encoding="utf-8")
        original = self.bridge(roots=[self.data], approver=lambda preview: True)
        operation = original.prepare_delete(str(target), permanent=False)
        deleted = original.commit_delete(operation["operation_id"])
        restricted = self.bridge(roots=[self.data], approver=lambda preview: False)
        with self.assertRaises(FileBridgeError):
            restricted.restore_recovery(deleted["recovery_id"])
        self.assertFalse(target.exists())
        self.assertEqual(len(restricted.list_recovery()["items"]), 1)


if __name__ == "__main__":
    unittest.main()
