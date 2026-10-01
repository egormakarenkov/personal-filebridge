import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class SourcePackageTests(unittest.TestCase):
    def test_source_archive_contains_install_and_agent_files(self):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run(
                [sys.executable, "-m", "build", "--sdist", "--outdir", output],
                cwd=PROJECT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = next(Path(output).glob("*.tar.gz"))
            with tarfile.open(archive, "r:gz") as package:
                paths = {member.name for member in package.getmembers()}
                entries = {Path(name).name for name in paths}
            self.assertTrue({"setup.ps1", "uninstall.ps1", "run-stdio.cmd", "install.cmd", "dashboard.cmd", "AGENT_GUIDE.md", "portable.py", "PersonalFilebridge.spec"} <= entries)
            self.assertFalse(any("docs/superpowers/" in name.replace("\\", "/") for name in paths))


if __name__ == "__main__":
    unittest.main()
