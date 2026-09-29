from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = PROJECT_ROOT / "r" / "requirements.tsv"
PREFLIGHT = PROJECT_ROOT / "r" / "preflight.R"
EXPORTER = PROJECT_ROOT / "r" / "export_features.R"


class RDependencyPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rscript = shutil.which("Rscript")
        if cls.rscript is None:
            raise unittest.SkipTest("Rscript is unavailable")
        available = subprocess.run([cls.rscript, "--vanilla", "-e",
            "quit(status=if (all(vapply(c('data.table','jsonlite'), requireNamespace, logical(1), quietly=TRUE))) 0 else 1)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if available.returncode:
            raise unittest.SkipTest("R exporter dependencies are unavailable; the R CI job installs them")

    def run_r(self, expression: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([self.rscript, "--vanilla", "-e", expression, *(str(value) for value in arguments)],
            cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_supported_runtime_and_actual_dependency_versions_are_recorded(self) -> None:
        result = self.run_r(
            "source(commandArgs(TRUE)[1]); versions <- run_dependency_preflight(commandArgs(TRUE)[2]); "
            "cat(jsonlite::toJSON(as.list(versions), auto_unbox=TRUE))", PREFLIGHT, REQUIREMENTS)
        self.assertEqual(result.returncode, 0, result.stderr)
        versions = json.loads(result.stdout)
        self.assertEqual(set(versions), {"data.table", "jsonlite"})
        self.assertTrue(all(isinstance(version, str) for version in versions.values()))

    def test_current_bioconductor_r_release_is_not_rejected_by_an_old_patch_pin(self) -> None:
        result = self.run_r(
            "source(commandArgs(TRUE)[1]); stopifnot(assert_supported_r_version('4.6.0') == '4.6.0'); "
            "stopifnot(assert_supported_r_version('4.6.1') == '4.6.1'); "
            "tryCatch({assert_supported_r_version('4.4.9'); quit(status=2)}, "
            "error=function(e) cat(conditionMessage(e)))", PREFLIGHT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("need R >= 4.5.0", result.stdout)

    def test_old_or_missing_dependency_fails_with_actionable_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / "requirements.tsv"
            requirements.write_text("package\tminimum_version\ndata.table\t999.0.0\njsonlite\t1.8.0\n", encoding="utf-8")
            result = self.run_r("source(commandArgs(TRUE)[1]); run_dependency_preflight(commandArgs(TRUE)[2])", PREFLIGHT, requirements)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data.table: need >= 999.0.0; found", result.stderr)
        self.assertIn("install_spliceimpactr.sh", result.stderr)

    def test_export_manifest_records_actual_versions(self) -> None:
        configured_cache = os.environ.get("TRANSCRIPT_BROWSER_TEST_CACHE")
        if not configured_cache:
            self.skipTest("Set TRANSCRIPT_BROWSER_TEST_CACHE to test an actual RDS export")
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            identifiers = temporary / "transcripts.txt"
            identifiers.write_text("ENST00000327443\nENST00000426431\nENST00000548560\nENST00000551969\n", encoding="ascii")
            output = temporary / "features"
            result = subprocess.run([self.rscript, "--vanilla", str(EXPORTER), "--input", configured_cache,
                "--output", str(output), "--transcripts", str(identifiers)], cwd=PROJECT_ROOT,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "feature_export_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["dependency_requirements"], "requirements.tsv")
        self.assertEqual(manifest["minimum_r_version"], "4.5.0")
        self.assertEqual(manifest["dependencies"]["data.table"], manifest["data_table_version"])
        self.assertEqual(manifest["dependencies"]["jsonlite"], manifest["jsonlite_version"])


if __name__ == "__main__":
    unittest.main()
