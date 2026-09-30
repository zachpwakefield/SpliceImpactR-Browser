from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_publication as audit


class PublicationAuditTests(unittest.TestCase):
    def test_browser_license_metadata_matches_owner_selected_mit(self) -> None:
        root = Path(__file__).resolve().parents[2]
        license_text = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn("The above copyright notice and this permission notice", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)
        metadata = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["license"], "MIT")
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("[MIT License](LICENSE)", readme)
        self.assertNotIn("source still needs an explicit license", readme)
        notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("The package is licensed `GPL-3`", notices)

    def test_ignored_runtime_data_is_allowed_but_staged_data_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/data/cache/\n/*.rds\n", encoding="utf-8")
            (root / "README.md").write_text("Public setup instructions\n", encoding="utf-8")
            generated = root / "data" / "cache" / "interpro.rds"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"synthetic generated input")
            scratch = root / "scratch.rds"
            scratch.write_bytes(b"synthetic root-level scratch input")
            with patch.object(audit, "ROOT", root), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.main(), 0)
                self.assertNotIn(generated, audit.iter_files())
                self.assertNotIn(scratch, audit.iter_files())
            subprocess.run(["git", "add", "-f", "data/cache/interpro.rds", "scratch.rds"], cwd=root, check=True)
            error = io.StringIO()
            with patch.object(audit, "ROOT", root), contextlib.redirect_stderr(error):
                self.assertEqual(audit.main(), 1)
            self.assertIn("generated/local artifact", error.getvalue())
            self.assertIn("generated scientific input: scratch.rds", error.getvalue())

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

    def test_force_staged_app_and_runtime_manifest_are_rejected_outside_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("*.app/\n", encoding="utf-8")
            generated = root / "custom-output/Local.app/Contents/Resources/Runtime-manifest.json"
            generated.parent.mkdir(parents=True)
            generated.write_text("{}", encoding="utf-8")
            subprocess.run(["git", "add", "-f", str(generated.relative_to(root))], cwd=root, check=True)
            (root / "Runtime.zip").write_bytes(b"synthetic private archive")
            error = io.StringIO()
            with patch.object(audit, "ROOT", root), contextlib.redirect_stderr(error):
                self.assertEqual(audit.main(), 1)
            self.assertIn("private/generated desktop runtime", error.getvalue())
            self.assertIn("Runtime.zip", error.getvalue())

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
