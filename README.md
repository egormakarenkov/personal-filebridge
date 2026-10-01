# Personal Filebridge

Personal Filebridge is a local MCP server for inspecting, editing, deleting, and restoring files in folders you select. It is a **Windows 11 source release candidate** for technical users. Installation currently uses Python and PowerShell; there is no bundled `.exe` installer or signed binary.

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

Download or clone this repository to a folder you control. In PowerShell, open that folder and run:

```powershell
.\setup.ps1
```

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

Then restart Codex and call `health`. For another MCP client, configure a stdio server that runs `.venv\Scripts\python.exe -m filebridge.server --transport stdio` from this source folder. `run-stdio.cmd` is provided for clients that accept batch-file commands. There is no HTTP listener in V1.

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

GitHub Actions runs tests and checks source and wheel distributions on Windows. A source-first release needs a clean Windows installation check before publishing: install, configure a disposable root, call `health`, inspect and read a test file, prepare and approve a change, restore it, and uninstall. There is no bundled executable at this stage.

## Uninstall

```powershell
.\uninstall.ps1
```

The script asks before removing Codex registration or the private Python environment. By default it retains local state and recovery files. To also be prompted separately for permanent removal of each local data directory, run `./uninstall.ps1 -RemoveLocalData`. Inspect recovery files before choosing that option. The script leaves the source folder in place.

## Troubleshooting

- **`health` is missing:** restart the MCP client and check its server registration. Confirm `run-stdio.cmd` points to this source folder and setup created `.venv`.
- **Configuration error:** rerun setup and select an existing folder. Verify `%LOCALAPPDATA%\PersonalFilebridge\config.json` is valid JSON with a nonempty `allowed_roots` array.
- **Path denied:** the requested path must be within a selected folder. The bridge also rejects protected service state, reparse points, and unsafe paths.
- **Commit denied or times out:** bring this Windows desktop forward and approve the dialog before the operation expires. A remote client cannot approve it by itself.
- **Recoverable deletion did not free space:** recovery may be on the same drive. Inspect and move or remove recovered data yourself only after you no longer need it.

For vulnerability reports, see [SECURITY.md](SECURITY.md). Contributions are covered by [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
