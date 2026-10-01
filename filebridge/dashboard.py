"""Read-only local status dashboard. It never starts the MCP service."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from .server import default_recovery_dir, default_state_dir, load_allowed_roots


def _within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def load_dashboard_data(state_dir: Path, recovery_dir: Path) -> dict[str, Any]:
    """Read configuration and bounded operation metadata without file contents."""
    state_dir = Path(state_dir)
    recovery_dir = Path(recovery_dir)
    result: dict[str, Any] = {
        "status": "Setup required", "allowed_roots": [], "audit": [], "recovery": [],
        "state_dir": str(state_dir), "recovery_dir": str(recovery_dir),
    }
    try:
        roots = load_allowed_roots(state_dir)
        result["allowed_roots"] = [str(root) for root in roots]
        result["status"] = "Configured" if all(root.is_dir() for root in roots) else "Folder missing"
    except (ValueError, OSError):
        return result

    audit_path = state_dir / "audit.jsonl"
    try:
        with audit_path.open("r", encoding="utf-8") as stream:
            recent = deque(stream, maxlen=100)
        for line in recent:
            try:
                item = json.loads(line)
                if isinstance(item, dict) and isinstance(item.get("action"), str):
                    result["audit"].append({key: item.get(key) for key in ("time_utc", "action", "path", "result")})
            except (ValueError, TypeError):
                continue
        result["audit"] = result["audit"][-50:]
    except (FileNotFoundError, PermissionError, OSError, UnicodeError):
        pass

    try:
        manifests = sorted(recovery_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for manifest_path in manifests:
            if len(result["recovery"]) >= 100:
                break
            try:
                item = json.loads(manifest_path.read_text(encoding="utf-8"))
                recovery_id = str(uuid.UUID(item["recovery_id"]))
                original = Path(item["original_path"])
                if not original.is_absolute() or not any(_within(original, root) for root in roots):
                    continue
                if not (recovery_dir / recovery_id).exists():
                    continue
                result["recovery"].append({
                    "recovery_id": recovery_id, "original_path": str(original),
                    "operation": item.get("operation", "unknown"), "created_at": item.get("created_at"),
                })
            except (KeyError, ValueError, TypeError, OSError, UnicodeError):
                continue
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return result


def _timestamp(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def show_dashboard(data: dict[str, Any]) -> None:
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("Personal Filebridge")
    window.geometry("850x560")
    window.minsize(650, 420)
    body = ttk.Frame(window, padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Personal Filebridge", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(body, text=f"Status: {data['status']}  •  File changes need approval on this PC").pack(anchor="w", pady=(2, 12))
    notebook = ttk.Notebook(body)
    notebook.pack(fill="both", expand=True)

    def add_list(title: str, rows: list[str]) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=title)
        listing = tk.Listbox(frame, font=("Consolas", 10), activestyle="none")
        listing.pack(fill="both", expand=True)
        for row in rows:
            listing.insert("end", row)

    add_list("Allowed folders", data["allowed_roots"] or ["No folders configured. Run install.cmd to set up access."])
    add_list("Recent activity", [
        f"{_timestamp(item.get('time_utc'))}  {item.get('action', '')}  {item.get('result', '')}  {item.get('path', '')}"
        for item in reversed(data["audit"])
    ] or ["No recorded operations."])
    add_list("Recoverable items", [
        f"{_timestamp(item.get('created_at'))}  {item['original_path']}  [{item['recovery_id']}]"
        for item in data["recovery"]
    ] or ["No recoverable items in the currently allowed folders."])

    footer = ttk.Frame(body)
    footer.pack(fill="x", pady=(12, 0))
    ttk.Label(footer, text="This dashboard shows metadata only. Restore through the MCP client and local approval.").pack(side="left")
    if os.name == "nt" and Path(data["recovery_dir"]).is_dir():
        ttk.Button(footer, text="Open recovery folder", command=lambda: os.startfile(data["recovery_dir"])).pack(side="right")
    window.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Personal Filebridge dashboard")
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--recovery-dir", type=Path, default=default_recovery_dir())
    parser.add_argument("--check", action="store_true", help="print status without opening a window")
    args = parser.parse_args()
    data = load_dashboard_data(args.state_dir, args.recovery_dir)
    if args.check:
        print(json.dumps({"status": data["status"], "allowed_roots": data["allowed_roots"],
                          "recent_operations": len(data["audit"]), "recoverable_items": len(data["recovery"])}))
    else:
        show_dashboard(data)


if __name__ == "__main__":
    main()
