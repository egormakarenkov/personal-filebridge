"""Local stdio MCP adapter for FileBridge."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .approval import request_local_approval
from .core import FileBridge


def default_state_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PersonalFilebridge"


def default_recovery_dir() -> Path:
    return Path.home() / "Filebridge Recovery"


def load_allowed_roots(state_dir: Path) -> list[Path]:
    """Read the user's selected roots; missing or malformed config denies startup."""
    config_path = state_dir / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Valid file access configuration required at {config_path}") from exc
    roots = config.get("allowed_roots") if isinstance(config, dict) else None
    if not isinstance(roots, list) or not roots:
        raise ValueError(f"Configure at least one allowed root in {config_path}")
    if any(not isinstance(root, str) or not root or not Path(root).is_absolute() for root in roots):
        raise ValueError(f"All allowed roots in {config_path} must be absolute paths")
    return [Path(root) for root in roots]


def make_server(bridge: FileBridge) -> MCPServer:
    mcp = MCPServer(
        name="personal-filebridge",
        version="0.1.0",
        instructions=(
            "Inspect a target before changing it. For writes and deletes, prepare first and "
            "show the exact path and effect to the user. Commit requires a separate approval "
            "on the local Windows desktop. Permanent deletion cannot be restored."
        ),
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    @mcp.tool(annotations=read)
    def health() -> dict[str, Any]:
        """Check that the local Windows file service is running."""
        return {"status": "ok", "service": "personal-filebridge"}

    @mcp.tool(annotations=read)
    def inspect_path(path: str) -> dict[str, Any]:
        """Inspect an absolute path under one of the configured allowed roots."""
        return bridge.inspect_path(path)

    @mcp.tool(annotations=read)
    def list_directory(path: str, recursive: bool = False, limit: int = 200) -> dict[str, Any]:
        """List up to 500 entries under an allowed directory."""
        return bridge.list_directory(path, recursive=recursive, limit=limit)

    @mcp.tool(annotations=read)
    def read_text(path: str, max_bytes: int = FileBridge.MAX_TEXT_BYTES) -> dict[str, Any]:
        """Read a UTF-8 file up to 4 MiB and return its revision hash."""
        return bridge.read_text(path, max_bytes=max_bytes)

    @mcp.tool(annotations=read)
    def read_base64(path: str, max_bytes: int = FileBridge.MAX_TEXT_BYTES) -> dict[str, Any]:
        """Read a binary file up to 4 MiB as base64 with its revision hash."""
        return bridge.read_base64(path, max_bytes=max_bytes)

    @mcp.tool(annotations=write)
    def prepare_write_text(path: str, text: str, expected_sha256: str | None = None) -> dict[str, Any]:
        """Stage a UTF-8 replacement; existing files require their current SHA-256."""
        return bridge.prepare_write_text(path, text, expected_sha256)

    @mcp.tool(annotations=write)
    def prepare_write_base64(path: str, content_base64: str, expected_sha256: str | None = None) -> dict[str, Any]:
        """Stage a binary replacement; existing files require their current SHA-256."""
        return bridge.prepare_write_base64(path, content_base64, expected_sha256)

    @mcp.tool(annotations=destructive)
    def commit_write(operation_id: str) -> dict[str, Any]:
        """Request local owner approval, then apply a staged edit."""
        return bridge.commit_write_text(operation_id)

    @mcp.tool(annotations=write)
    def prepare_delete(path: str, permanent: bool = False) -> dict[str, Any]:
        """Stage deletion of an exact file or directory path."""
        return bridge.prepare_delete(path, permanent=permanent)

    @mcp.tool(annotations=destructive)
    def commit_delete(operation_id: str) -> dict[str, Any]:
        """Request local owner approval, then delete a staged path."""
        return bridge.commit_delete(operation_id)

    @mcp.tool(annotations=read)
    def list_recovery(limit: int = 100) -> dict[str, Any]:
        """List saved prior versions and recoverable deleted items."""
        return bridge.list_recovery(limit=limit)

    @mcp.tool(annotations=write)
    def restore_recovery(recovery_id: str) -> dict[str, Any]:
        """Request local owner approval, then restore if the original path is absent."""
        return bridge.restore_recovery(recovery_id)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Windows file MCP service")
    parser.add_argument("--transport", choices=("stdio", "init"), default="stdio")
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--recovery-dir", type=Path, default=default_recovery_dir())
    args = parser.parse_args()
    if args.transport == "init":
        print(f"State: {args.state_dir}\nRecovery: {args.recovery_dir}\nConfig: {args.state_dir / 'config.json'}")
        return
    roots = load_allowed_roots(args.state_dir)
    bridge = FileBridge(args.state_dir, args.recovery_dir, allowed_roots=roots, approver=request_local_approval)
    make_server(bridge).run(transport="stdio")


if __name__ == "__main__":
    main()
