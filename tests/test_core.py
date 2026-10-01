import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from filebridge.core import FileBridge, FileBridgeError


class FileBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "outside-workspace"
        self.data.mkdir()
        self.bridge = FileBridge(
            self.root / "state", self.root / "recovery",
            allowed_roots=[self.data], approver=lambda preview: True,
        )

    def test_read_write_and_restore(self):
        path = self.data / "note.txt"
        path.write_text("before", encoding="utf-8")
        read = self.bridge.read_text(str(path))
        self.assertEqual(read["text"], "before")
        prepared = self.bridge.prepare_write_text(str(path), "after", read["sha256"])
        done = self.bridge.commit_write_text(prepared["operation_id"])
        self.assertEqual(path.read_text(encoding="utf-8"), "after")
        self.assertIsNotNone(done["recovery_id"])
        path.unlink()
        restored = self.bridge.restore_recovery(done["recovery_id"])
        self.assertEqual(restored["path"], str(path))
        self.assertEqual(path.read_text(encoding="utf-8"), "before")

    def test_write_refuses_revision_conflict(self):
        path = self.data / "note.txt"
        path.write_text("one", encoding="utf-8")
        digest = hashlib.sha256(b"one").hexdigest()
        prepared = self.bridge.prepare_write_text(str(path), "two", digest)
        path.write_text("changed", encoding="utf-8")
        with self.assertRaises(FileBridgeError):
            self.bridge.commit_write_text(prepared["operation_id"])
        self.assertEqual(path.read_text(encoding="utf-8"), "changed")

    def test_new_file_requires_absent_target(self):
        path = self.data / "new.txt"
        prepared = self.bridge.prepare_write_text(str(path), "new", None)
        path.write_text("other", encoding="utf-8")
        with self.assertRaises(FileBridgeError):
            self.bridge.commit_write_text(prepared["operation_id"])

    def test_recoverable_and_permanent_delete(self):
        folder = self.data / "folder"
        folder.mkdir()
        (folder / "item.txt").write_text("x", encoding="utf-8")
        prepared = self.bridge.prepare_delete(str(folder), permanent=False)
        self.assertEqual(prepared["entries"], 2)
        self.assertEqual(prepared["estimated_bytes"], 1)
        done = self.bridge.commit_delete(prepared["operation_id"])
        self.assertFalse(folder.exists())
        self.bridge.restore_recovery(done["recovery_id"])
        self.assertEqual((folder / "item.txt").read_text(encoding="utf-8"), "x")

        prepared = self.bridge.prepare_delete(str(folder), permanent=True)
        done = self.bridge.commit_delete(prepared["operation_id"])
        self.assertTrue(done["permanent"])
        self.assertFalse(folder.exists())

    def test_rejects_relative_roots_and_state_paths(self):
        for path in ["relative.txt", str(Path(self.temp.name).anchor), str(self.root / "state")]:
            with self.subTest(path=path), self.assertRaises(FileBridgeError):
                self.bridge.inspect_path(path)

    def test_directory_listing_is_bounded(self):
        for name in ["a.txt", "b.txt", "c.txt"]:
            (self.data / name).write_text(name, encoding="utf-8")
        result = self.bridge.list_directory(str(self.data), limit=2)
        self.assertEqual(len(result["entries"]), 2)
        self.assertTrue(result["truncated"])

    def test_binary_edit_and_state_parent_listing(self):
        self.bridge.list_directory(str(self.data), limit=10)
        path = self.data / "blob.bin"
        path.write_bytes(b"\x00\xff")
        read = self.bridge.read_base64(str(path))
        self.assertEqual(read["base64"], "AP8=")
        prepared = self.bridge.prepare_write_base64(str(path), "AQI=", read["sha256"])
        self.bridge.commit_write_text(prepared["operation_id"])
        self.assertEqual(path.read_bytes(), b"\x01\x02")

    def test_rejects_deleting_state_parent(self):
        with self.assertRaises(FileBridgeError):
            self.bridge.prepare_delete(str(self.root), permanent=True)

    def test_restore_refuses_collision(self):
        path = self.data / "gone.txt"
        path.write_text("original", encoding="utf-8")
        prepared = self.bridge.prepare_delete(str(path), permanent=False)
        done = self.bridge.commit_delete(prepared["operation_id"])
        path.write_text("replacement", encoding="utf-8")
        with self.assertRaises(FileBridgeError):
            self.bridge.restore_recovery(done["recovery_id"])

    def test_delete_refuses_changed_directory_contents(self):
        folder = self.data / "changing"
        folder.mkdir()
        child = folder / "item.txt"
        child.write_text("old", encoding="utf-8")
        prepared = self.bridge.prepare_delete(str(folder), permanent=True)
        child.write_text("new content", encoding="utf-8")
        with self.assertRaises(FileBridgeError):
            self.bridge.commit_delete(prepared["operation_id"])
        self.assertTrue(child.exists())

    def test_expired_operation_cannot_commit(self):
        target = self.data / "later.txt"
        prepared = self.bridge.prepare_write_text(str(target), "hello", None)
        self.bridge.operations[prepared["operation_id"]]["expires_at"] = 0
        with self.assertRaises(FileBridgeError):
            self.bridge.commit_write_text(prepared["operation_id"])
        self.assertFalse(target.exists())

    def test_symlink_is_refused_when_windows_allows_creating_one(self):
        target = self.data / "target.txt"
        target.write_text("secret", encoding="utf-8")
        link = self.data / "link.txt"
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("Windows symlink creation is not enabled")
        with self.assertRaises(FileBridgeError):
            self.bridge.read_text(str(link))


if __name__ == "__main__":
    unittest.main()
