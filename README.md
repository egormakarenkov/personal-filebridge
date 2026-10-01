# Personal Filebridge

Personal Filebridge is a local MCP server for inspecting, editing, deleting, and restoring files in folders you select. It is a **Windows 11 release candidate** with a double-click setup launcher and read-only dashboard. The source installation requires Python 3.13 or newer. The portable Windows build bundles Python so users do not need to install it. The portable executable is unsigned and still needs a clean interactive installation check before a stable release.

The server runs as your Windows account. It cannot bypass Windows permissions, UAC, file locks, organization policy, or MCP host policy. It connects over **local stdio**. Public network hosting and unattended phone approval are outside V1.

## What it does

- Inspect, list, and read files under configured folder roots.
- Prepare an edit or deletion, then require a separate local owner approval dialog before committing it. Restoring a saved item also requires local approval. If the dialog cannot open or times out, the change is denied.
- Keep prior versions of edited files and support recoverable deletion and restoration. Permanent deletion is an explicit separate choice and is irreversible through Filebridge.
- Record operation metadata in a local audit log without file contents.

The MCP client can read files inside your chosen roots, so choose folders narrowly and connect only a client you trust. The owner dialog protects commits; it does not make an untrusted client safe to read private files. The bridge cannot defend against another program already running arbitrary code as your Windows account.

## Requirements

- Windows 11 with an interactive desktop for approving changes.
- Python 3.13 or newer, with `py` or `python` available in PowerShell.
- Internet access during setup to install Python dependencies.
- A local MCP client that supports stdio, such as Codex. `codex` on your path is optional for automatic registration.

## Install from source

Download the repository ZIP from GitHub or clone it to a folder you control, then extract it. Alternatively, download the portable Windows ZIP from a release or CI artifact and extract the whole folder, including `_internal`; moving the executable alone will break it. On Windows, double-click `install.cmd`. The window stays open to show any setup error. For a PowerShell installation, open the source folder and run:

```powershell
.\setup.ps1
```

The portable ZIP uses `PersonalFilebridge.exe` and needs no Python installation. Source setup stops before creating an environment if Python 3.13 or newer is missing. Select only folders you want the connected MCP client to read and modify. Setup may ask you to confirm before replacing a previous Filebridge configuration.

The installer asks for one or more **existing absolute folder paths** to allow, then creates `.venv`, installs dependencies, and writes `%LOCALAPPDATA%\PersonalFilebridge\config.json`. On a fresh install, it restricts the state and recovery directories and config file to your Windows account. Existing child files may retain older permissions; inspect them if you are migrating from an earlier installation. It refuses an empty list, drive roots, and link or reparse-point roots. If the Codex CLI is available, it registers the private Python environment as an MCP server named `personal-filebridge`. If that name is already registered, setup leaves it unchanged and tells you to review it. Restart your MCP client after registration.

The config has this shape (the example paths are illustrative):

```json
{
  "allowed_roots": ["C:\\Users\\You\\Documents\\BridgeFiles"]
}
```

The server fails closed if the config is missing or invalid. You may edit the allowed roots in that local file or rerun setup. Keep the paths as absolute directories, and restart the MCP server after changing them. Config, state, audit logs, and recovered files stay outside the repository and must not be committed to Git.

To register manually with Codex, run this from PowerShell using the absolute path to your copy:

```powershell
codex mcp add personal-filebridge -- "C:\absolute\path\to\filebridge\.venv\Scripts\python.exe" -m filebridge.server --transport stdio
```

Then restart Codex and call `health`. For another MCP client, configure a stdio server using `run-stdio.cmd` from the installed folder. Source installations can also run `.venv\Scripts\python.exe -m filebridge.server --transport stdio`; portable installations can run `PersonalFilebridge.exe --transport stdio`. There is no HTTP listener in V1.

For model-facing usage instructions, see [Agent guide](docs/AGENT_GUIDE.md). You can attach that file to a ChatGPT or Claude conversation, but a guide does not connect tools: the client must separately support and connect a local stdio MCP server. The server also exposes its essential workflow through MCP instructions and tool descriptions, although each client decides how to present them.

## Local dashboard

After setup, double-click `dashboard.cmd` to see the configured folders, recent operation metadata, and recoverable items. The dashboard is read-only: it does not edit configuration, read personal file contents, restore files, or approve actions. Restore through the MCP client and the local approval dialog. For a quick status check without opening a window, run:

```powershell
.\.venv\Scripts\python.exe -m filebridge.dashboard --check
```

## File operations and approval

1. Inspect or read the exact target. File reads return a SHA-256 revision.
2. Prepare a write using that revision, or prepare a deletion. A deletion preview reports the target, estimated bytes, and entry count. Nothing is changed during preparation.
3. Review the prepared operation. At commit, a **Windows dialog on this PC** shows the target, action, size, entry count, permanence, and expiry. Approve or deny it locally. A phrase supplied through the MCP client is not human consent.
4. For recoverable changes, use `list_recovery` and `restore_recovery` when needed. Restoration requires the original path to be vacant and a local approval.

Prepared operations expire after ten minutes; at most 64 can be pending, and replacement bytes are held only in the running server's memory. A service restart loses pending operations. The bridge rechecks target contents at commit to reject changes made since preparation. Text and binary reads and writes are limited to 4 MiB per call; larger files can be inspected and deleted. Large directory previews have a bounded entry count. The service does not run shell commands.

Recoverable deletion moves the target into `%USERPROFILE%\Filebridge Recovery`. Recovered files and saved prior versions are **plaintext copies**; anyone who can access that Windows account or directory can read them. They consume disk space and, when recovery is on the same drive, deletion may not reclaim space until the saved item is removed. Permanent deletion cannot be restored through Filebridge. Review the dialog carefully before approving it.

**Remote sessions:** A commit needs a person at this PC to approve the local dialog. If you cannot see or reach the desktop, it is denied. Do not depend on this release for unattended remote file changes.

## Test and build

The automated tests use disposable directories. They should not touch personal files.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install build
.\.venv\Scripts\python.exe -m build
```

GitHub Actions runs tests, source-package checks, a disposable setup, distribution checks, and a portable executable smoke test on Windows. A stable release also needs the human checks in [Release checklist](docs/RELEASE_CHECKLIST.md), especially a clean interactive install and approval-dialog walkthrough.

## Uninstall

```powershell
.\uninstall.ps1
```

The script asks before removing Codex registration or the private Python environment. By default it retains local state and recovery files. To also be prompted separately for permanent removal of each local data directory, run `./uninstall.ps1 -RemoveLocalData`. Inspect recovery files before choosing that option. The script leaves the source folder in place.

## Troubleshooting

- **`health` is missing:** restart the MCP client and check its server registration. Confirm `run-stdio.cmd` points to this source folder and setup created `.venv`.
- **Install reports Python missing:** for source installation, install Python 3.13 or newer with the Python launcher or `python` on your path, then rerun `install.cmd`. The portable ZIP does not need Python.
- **Dashboard does not open:** run `dashboard.cmd` after setup. If Python reports that Tkinter is unavailable, install a Python build that includes Tk support.
- **Configuration error:** rerun setup and select an existing folder. Verify `%LOCALAPPDATA%\PersonalFilebridge\config.json` is valid JSON with a nonempty `allowed_roots` array.
- **Path denied:** the requested path must be within a selected folder. The bridge also rejects protected service state, reparse points, and unsafe paths.
- **Commit denied or times out:** bring this Windows desktop forward and approve the dialog before the operation expires. A remote client cannot approve it by itself.
- **Recoverable deletion did not free space:** recovery may be on the same drive. Inspect and move or remove recovered data yourself only after you no longer need it.

For vulnerability reports, see [SECURITY.md](SECURITY.md). Contributions are covered by [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
