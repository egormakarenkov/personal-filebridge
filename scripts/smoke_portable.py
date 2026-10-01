"""Disposable protocol smoke check for a PyInstaller Windows build."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def check(executable: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        state = base / "state"
        state.mkdir()
        allowed = base / "allowed"
        allowed.mkdir()
        recovery = base / "recovery"
        target = allowed / "smoke.txt"
        target.write_text("before", encoding="utf-8")
        (state / "config.json").write_text(json.dumps({"allowed_roots": [str(allowed)]}), encoding="utf-8")
        params = StdioServerParameters(
            command=str(executable.resolve()),
            args=["--transport", "stdio", "--state-dir", str(state), "--recovery-dir", str(recovery)],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                health = await session.call_tool("health", {})
                assert not health.is_error, str(health)
                inspected = await session.call_tool("read_text", {"path": str(target)})
                assert not inspected.is_error and inspected.structured_content["text"] == "before", str(inspected)
                prepared = await session.call_tool("prepare_write_text", {
                    "path": str(target), "text": "after", "expected_sha256": inspected.structured_content["sha256"],
                })
                assert not prepared.is_error, str(prepared)
                assert target.read_text(encoding="utf-8") == "before"
                print("Portable MCP handshake, read, and prepare: OK")


if __name__ == "__main__":
    asyncio.run(check(Path(sys.argv[1])))
