"""Entry point shared by source tests and the portable Windows executable."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--approval-dialog":
        sys.argv.pop(1)
        from filebridge.approval import main as approval_main
        approval_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "--dashboard":
        sys.argv.pop(1)
        from filebridge.dashboard import main as dashboard_main
        dashboard_main()
    else:
        from filebridge.server import main as server_main
        server_main()


if __name__ == "__main__":
    main()
