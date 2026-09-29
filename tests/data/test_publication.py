from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_publication as audit


class PublicationAuditTests(unittest.TestCase):
    def test_ignored_runtime_data_is_allowed_but_staged_data_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/data/cache/\n", encoding="utf-8")
            (root / "README.md").write_text("Public setup instructions\n", encoding="utf-8")
            generated = root / "data" / "cache" / "interpro.rds"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"synthetic generated input")
            with patch.object(audit, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.main(), 0)
                self.assertNotIn(generated, audit.iter_files())
            subprocess.run(["git", "add", "-f", "data/cache/interpro.rds"], cwd=root, check=True)
            error = io.StringIO()
            with patch.object(audit, "ROOT", root), contextlib.redirect_stderr(error):
                self.assertEqual(audit.main(), 1)
            self.assertIn("generated/local artifact", error.getvalue())

    def test_private_paths_and_credentials_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            # Construct deliberately invalid content without putting private
            # path/credential-like examples into the public source itself.
            private_path = "/".join(("", "Users", "example", "data"))
            credential = "api" + "_key" + ' = "synthetic-example"'
            (root / "bad.md").write_text(private_path + "\n" + credential, encoding="utf-8")
            error = io.StringIO()
            with patch.object(audit, "ROOT", root), contextlib.redirect_stderr(error):
                self.assertEqual(audit.main(), 1)
            self.assertIn("private/local path", error.getvalue())
            self.assertIn("credential-like assignment", error.getvalue())

    def test_zip_checkout_without_git_uses_source_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Public instructions", encoding="utf-8")
            cache = root / "data" / "cache"
            cache.mkdir(parents=True)
            (cache / "fixture.rds").write_bytes(b"synthetic input")
            with patch.object(audit, "ROOT", root), patch.object(audit.subprocess, "run", side_effect=FileNotFoundError):
                self.assertEqual(audit.iter_files(), [root / "README.md"])


if __name__ == "__main__":
    unittest.main()
