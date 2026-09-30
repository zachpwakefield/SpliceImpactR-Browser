from __future__ import annotations

from pathlib import Path
import plistlib
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.app.cli import build_parser
from backend.app.constants import APPLICATION_NAME
from backend.app.main import create_app
from backend.tests.test_api import make_package


class ApplicationBrandingTests(unittest.TestCase):
    def test_cli_api_and_missing_frontend_use_the_new_name(self) -> None:
        self.assertEqual(APPLICATION_NAME, "SpliceImpactR Browser")
        self.assertEqual(build_parser().prog, "spliceimpactr-browser")
        self.assertIn(APPLICATION_NAME, build_parser().description)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(project_root=root, package_root=make_package(root), dev_fixture=True)
            client = TestClient(app, base_url="http://127.0.0.1")
            self.assertEqual(client.get("/api/openapi.json").json()["info"]["title"], f"{APPLICATION_NAME} API")
            fallback = client.get("/")
            self.assertEqual(fallback.status_code, 503)
            self.assertIn(f"<title>{APPLICATION_NAME} API</title>", fallback.text)

    def test_native_names_agree_without_changing_legacy_data_identity(self) -> None:
        root = Path(__file__).resolve().parents[2]
        desktop = root / "desktop_app"
        metadata = plistlib.loads((desktop / "Info.plist").read_bytes())
        self.assertEqual(metadata["CFBundleName"], APPLICATION_NAME)
        self.assertEqual(metadata["CFBundleDisplayName"], APPLICATION_NAME)
        self.assertEqual(metadata["CFBundleExecutable"], "SpliceImpactRBrowserLauncher")
        self.assertEqual(metadata["CFBundleIdentifier"], "local.transcript-browser.launcher")
        source = (desktop / "SpliceImpactRBrowserLauncher.swift").read_text(encoding="utf-8")
        self.assertIn(f'private let applicationName = "{APPLICATION_NAME}"', source)
        self.assertIn('window.title = applicationName', source)
        self.assertIn('appendingPathComponent("Transcript Browser", isDirectory: true)', source)
        self.assertFalse((desktop / "TranscriptBrowserLauncher.swift").exists())
        for filename in ("build_macos_app.sh", "install_macos_app.sh"):
            script = (desktop / filename).read_text(encoding="utf-8")
            self.assertIn(f"{APPLICATION_NAME}.app", script)
            self.assertNotIn("/Transcript Browser.app", script)
        self.assertIn("SpliceImpactRBrowserLauncher.swift", (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
