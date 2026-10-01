# Security policy

Personal Filebridge handles local files and can permanently delete them. Please do not post a security vulnerability, local path, access token, or private file content in a public issue. Use GitHub's private vulnerability reporting for this repository when it is enabled. Until that channel is available, contact the maintainer privately through their GitHub profile.

This V1 is intended for a trusted MCP client on the same Windows PC. It runs as your Windows account and cannot elevate privileges, override Windows or organization policy, or stop software already running with your account's rights. File reads inside your selected roots are exposed to the connected MCP client. Writes, deletions, and restores require a local owner approval dialog; if the dialog is unavailable, the change is denied.

Do not expose the stdio server through an internet-facing tunnel or share local state and recovery directories. Review the allowed roots in `%LOCALAPPDATA%\PersonalFilebridge\config.json` and grant only the folders you need.
