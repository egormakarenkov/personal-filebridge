import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from filebridge.approval import _summary, request_local_approval
from filebridge.core import FileBridge
from filebridge.server import load_allowed_roots, make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = make_server(FileBridge(
            self.root / "state", self.root / "recovery", allowed_roots=[self.root], approver=lambda _: True,
        ))

    def test_tools_exist_and_health_works(self):
        async def run():
            tools = await self.server.list_tools()
            names = {tool.name for tool in tools}
            self.assertTrue({"health", "prepare_write_text", "commit_write", "prepare_delete", "commit_delete", "restore_recovery"} <= names)
            result = await self.server.call_tool("health", {})
            self.assertIn("ok", str(result))
            commit = next(tool for tool in tools if tool.name == "commit_delete")
            self.assertNotIn("confirmation", str(commit.input_schema))
        asyncio.run(run())

    def test_config_fails_closed(self):
        state = self.root / "config-state"
        state.mkdir()
        with self.assertRaises(ValueError):
            load_allowed_roots(state)
        for config in ({}, {"allowed_roots": []}, {"allowed_roots": ["relative"]}, {"allowed_roots": "C:\\"}):
            (state / "config.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_allowed_roots(state)
        (state / "config.json").write_text(json.dumps({"allowed_roots": [str(self.root)]}), encoding="utf-8")
        self.assertEqual(load_allowed_roots(state), [self.root])

    def test_local_approval_denies_on_unavailable_desktop_and_timeout(self):
        preview = {"operation_id": "123", "action": "delete", "path": str(self.root / "file")}
        with patch("filebridge.approval.subprocess.run", side_effect=OSError("no desktop")):
            self.assertFalse(request_local_approval(preview))
        with patch("filebridge.approval.subprocess.run", side_effect=subprocess.TimeoutExpired("python", 2)):
            self.assertFalse(request_local_approval(preview))
        with patch("filebridge.approval.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "APPROVED\n", "")):
            self.assertTrue(request_local_approval(preview))
        with patch("filebridge.approval.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assertFalse(request_local_approval(preview))

    def test_dialog_summary_includes_exact_effect(self):
        detail = _summary({
            "operation_id": "abc", "action": "delete", "path": "C:\\sample\\data", "permanent": True,
            "entries": 12, "estimated_bytes": 4096, "expires_in_seconds": 45,
        })
        for word in ("C:\\sample\\data", "PERMANENT", "12", "4,096", "45", "abc"):
            self.assertIn(word, detail)

    def test_stdio_protocol_round_trip(self):
        root = self.root
        disposable = root / "disposable.txt"
        disposable.write_text("before", encoding="utf-8")
        state = root / "transport-state"
        state.mkdir()
        (state / "config.json").write_text(json.dumps({"allowed_roots": [str(root)]}), encoding="utf-8")

        async def run():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "filebridge.server", "--transport", "stdio", "--state-dir", str(state), "--recovery-dir", str(root / "transport-recovery")],
            )
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertIn("health", {tool.name for tool in tools.tools})
                    response = await session.call_tool("health", {})
                    self.assertFalse(response.is_error)
                    self.assertIn("personal-filebridge", str(response))
                    read = await session.call_tool("read_text", {"path": str(disposable)})
                    self.assertFalse(read.is_error)
                    prepared = await session.call_tool("prepare_write_text", {
                        "path": str(disposable), "text": "after", "expected_sha256": read.structured_content["sha256"],
                    })
                    self.assertFalse(prepared.is_error)
                    self.assertEqual(disposable.read_text(encoding="utf-8"), "before")

        asyncio.run(run())

    def test_server_instructions_explain_revision_recovery_and_local_approval(self):
        instructions = self.server.instructions.lower()
        for required in ("sha-256", "recovery", "local windows", "prepare", "commit"):
            self.assertIn(required, instructions)

    def test_preview_version_is_distinct_from_published_v010(self):
        self.assertEqual(self.server.version, "0.2.0b1")

    def test_tool_lifecycle_with_disposable_file(self):
        target = self.root / "lifecycle.txt"
        target.write_text("first", encoding="utf-8")

        async def run():
            read = await self.server.call_tool("read_text", {"path": str(target)})
            revision = read.structured_content["sha256"]
            prepared = await self.server.call_tool("prepare_write_text", {
                "path": str(target), "text": "second", "expected_sha256": revision,
            })
            self.assertEqual(target.read_text(encoding="utf-8"), "first")
            changed = await self.server.call_tool("commit_write", {
                "operation_id": prepared.structured_content["operation_id"],
            })
            self.assertEqual(target.read_text(encoding="utf-8"), "second")
            self.assertTrue(changed.structured_content["recovery_id"])
            deletion = await self.server.call_tool("prepare_delete", {"path": str(target)})
            deleted = await self.server.call_tool("commit_delete", {
                "operation_id": deletion.structured_content["operation_id"],
            })
            self.assertFalse(target.exists())
            restored = await self.server.call_tool("restore_recovery", {
                "recovery_id": deleted.structured_content["recovery_id"],
            })
            self.assertFalse(restored.is_error)
            self.assertEqual(target.read_text(encoding="utf-8"), "second")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
