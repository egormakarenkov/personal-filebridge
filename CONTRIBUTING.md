# Contributing

Issues and pull requests are welcome for reproducible bugs, documentation, and tests. For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

This project targets Windows 11 and Python 3.13 or newer. Install development dependencies in a virtual environment, then run:

```powershell
python -m unittest discover -s tests -v
python -m build
```

Use disposable directories in tests. Do not include your local `config.json`, state, recovery data, tokens, audit logs, or real personal files in a pull request. Changes to file access or approval behavior should include a test of denied and unavailable approval, as well as the intended success case.

By submitting a contribution, you agree to license it under the repository's MIT license.
