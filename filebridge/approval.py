"""Owner approval on the local Windows desktop, separate from the MCP client."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


APPROVAL_TIMEOUT_SECONDS = 120


def request_local_approval(preview: dict[str, Any], timeout_seconds: int = APPROVAL_TIMEOUT_SECONDS) -> bool:
    """Ask the person at this PC to approve one operation; errors always deny."""
    if not isinstance(preview, dict) or not preview.get("path") or not preview.get("operation_id"):
        return False
    timeout_seconds = max(1, min(int(timeout_seconds), APPROVAL_TIMEOUT_SECONDS))
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "filebridge.approval", str(timeout_seconds)],
            input=json.dumps(preview, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 3,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "APPROVED"


def _summary(preview: dict[str, Any]) -> str:
    action = str(preview.get("action", preview.get("kind", "File operation"))).upper()
    path = str(preview.get("path", ""))
    lines = [f"Action: {action}", f"Target: {path}"]
    if "permanent" in preview:
        lines.append("Deletion: PERMANENT (cannot be restored)" if preview["permanent"] else "Deletion: Recoverable")
    if "entries" in preview:
        lines.append(f"Directory entries: {preview['entries']}")
    if "estimated_bytes" in preview:
        lines.append(f"Estimated size: {preview['estimated_bytes']:,} bytes")
    if action == "WRITE" and "size_bytes" in preview:
        lines.append(f"Replacement size: {preview['size_bytes']:,} bytes")
    if "expires_in_seconds" in preview:
        lines.append(f"Prepared operation expires in: {preview['expires_in_seconds']} seconds")
    lines.append(f"Operation ID: {preview.get('operation_id', '')}")
    return "\n".join(lines)


def _show_dialog(preview: dict[str, Any], timeout_seconds: int) -> bool:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Personal Filebridge: approve file operation")
    root.geometry("680x330")
    root.minsize(520, 290)
    root.attributes("-topmost", True)
    approved = False
    remaining = timeout_seconds

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Approve this file operation on your PC?", font=("Segoe UI", 13, "bold")).pack(anchor="w")
    details = tk.Text(frame, height=10, wrap="word", relief="flat", background=root.cget("background"))
    details.insert("1.0", _summary(preview))
    details.configure(state="disabled")
    details.pack(fill="both", expand=True, pady=10)
    countdown = ttk.Label(frame)
    countdown.pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e", pady=(8, 0))

    def close(allow: bool = False) -> None:
        nonlocal approved
        approved = allow
        root.destroy()

    ttk.Button(buttons, text="Deny", command=lambda: close(False)).pack(side="left", padx=8)
    ttk.Button(buttons, text="Approve", command=lambda: close(True)).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", lambda: close(False))

    def tick() -> None:
        nonlocal remaining
        countdown.configure(text=f"Automatically denied in {remaining} seconds")
        if remaining <= 0:
            close(False)
        else:
            remaining -= 1
            root.after(1000, tick)

    tick()
    root.mainloop()
    return approved


def main() -> None:
    try:
        timeout_seconds = max(1, min(int(sys.argv[1]), APPROVAL_TIMEOUT_SECONDS))
        preview = json.load(sys.stdin)
        if not isinstance(preview, dict):
            return
        if _show_dialog(preview, timeout_seconds):
            print("APPROVED")
    except Exception:
        # No interactive desktop, invalid input, or GUI failure: deny.
        return


if __name__ == "__main__":
    main()
