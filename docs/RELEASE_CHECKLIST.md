# Stable release checklist

The automated suite is necessary, but it cannot prove that the local approval dialog is visible and understandable to a person on another PC. Complete these checks before labeling a release stable.

## Automated gates

- Windows CI passes unit tests, MCP stdio handshake, lifecycle tests on disposable files, fresh setup, dashboard status, source archive checks, and wheel checks.
- Dependency alerts and private vulnerability reporting are enabled on the GitHub repository; known issues are reviewed.
- A clean source archive contains `install.cmd`, `setup.ps1`, `dashboard.cmd`, `uninstall.ps1`, the agent guide, and all Python modules.
- The release tag matches the package and MCP server versions. Release notes name supported Windows and Python versions, limitations, and any upgrade steps.

## Human checks on a clean Windows 11 PC

1. Download and extract the GitHub source archive. Run `install.cmd` without any prior Filebridge state. Confirm Python prerequisite messaging is clear, choose a disposable allowed folder, and check that setup finishes without elevated privileges.
2. Open `dashboard.cmd`. Confirm the chosen root appears, no personal file contents appear, and the recovery and activity tabs are readable.
3. Connect a supported local MCP client. Restart it, call `health`, then inspect and read a disposable file. Confirm a path outside the allowed folder is denied.
4. Prepare an edit. Confirm the file remains unchanged until commit. Check the local approval dialog's path, effect, expiry, and buttons. Deny once and verify no change; repeat and approve.
5. Prepare recoverable deletion of a disposable folder. Check the entry count and estimated size, approve locally, then restore through the MCP client and verify the contents.
6. Confirm permanent deletion is visibly marked irreversible in the preview and approval dialog. Use only disposable data.
7. Run `uninstall.ps1`. Confirm it leaves recovery files by default and does not remove a different MCP registration without clear confirmation.
8. Repeat setup over an existing installation to confirm the configuration replacement warning and recovery data behavior.

## Distribution and trust

The source distribution needs Python 3.13 or newer. The portable ZIP bundles Python but is unsigned; code signing requires a publisher identity. Do not label either download stable before the interactive checks above. Explain possible Windows download warnings. Remote unattended approval is outside this release; local desktop approval is required for every mutation.
