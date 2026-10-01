# Agent guide for Personal Filebridge

Personal Filebridge gives an MCP client access to selected folders on a local Windows PC. It cannot elevate privileges or bypass client policy. Reads may expose private content to the connected client. Use the smallest folder scope needed and follow the user's instructions and your host's rules.

## Connect and check

After installation, restart the MCP client and call `health`. If the tool is missing, check client registration and `run-stdio.cmd`. The server communicates over local stdio; it has no public HTTP endpoint. For clients other than Codex, configure a local stdio MCP server that runs `run-stdio.cmd` from the installed source folder. See the README for the equivalent Python command.

## Workflow for changes

1. Call `inspect_path` or `list_directory` for the exact absolute target. For an existing file edit, call `read_text` or `read_base64` and retain its `sha256` value.
2. Call `prepare_write_text`, `prepare_write_base64`, or `prepare_delete`. For an existing file edit, supply the observed `sha256` as `expected_sha256`. A new file omits it. Deletion defaults to recoverable; use `permanent=true` only when explicitly requested or when retaining a recovery copy would defeat the user's stated goal.
3. Show the user the prepared target and effect. For a directory deletion include the reported entry count and estimated bytes. Explain whether recovery is available. Obtain any chat approval required by the user or MCP host.
4. Call `commit_write` or `commit_delete` using the operation ID while it is valid. A separate local Windows dialog asks the PC owner to approve the exact action. If it is unavailable, denied, or times out, the change does not proceed. A remote chat message is not a substitute for this dialog.
5. Verify the result with `inspect_path` or a read. Report the `recovery_id` or saved prior version when returned. Use `list_recovery` and `restore_recovery` only for items within the currently allowed roots; restoring also needs local owner approval.

Prepared operations expire after ten minutes. If the target changes after preparation, prepare again. File reads and writes are limited to 4 MiB per call. The service does not run shell commands. Never ask it to operate outside the configured roots or to expose local service state.

## Example requests

- “Inspect this folder and tell me what is using space. Do not delete anything yet.”
- “Replace this text file after reading its current revision. Show me the prepared change before committing.”
- “Prepare a recoverable deletion of this exact folder and report its size and entry count.”

For ChatGPT or Claude, attach this file to the conversation if you want the model to see the extended guidance. This file does not connect the tools by itself: the client must support and connect a local stdio MCP server. The server also supplies concise MCP instructions and tool descriptions, but each client decides how to display them.
