from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.builder import build


class PreparedSourceIntegrityTests(unittest.TestCase):
    def test_source_bytes_and_sizes_are_verified_not_just_declared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_bytes = b"synthetic raw input"
            feature_bytes = b"synthetic RDS bytes for an integrity unit test"
            (root / "raw.gz").write_bytes(raw_bytes)
            feature = root / "pfam.rds"
            feature.write_bytes(feature_bytes)
            (root / build.PREPARATION_MANIFEST).write_text("{}", encoding="utf-8")
            preparation = {
                "raw_inputs": {"raw.gz": {"size": len(raw_bytes)}},
                "feature_sources": {"pfam": {
                    "size": len(feature_bytes),
                    "sha256": hashlib.sha256(feature_bytes).hexdigest(),
                }},
            }
            with patch.object(build, "REQUIRED_INPUTS", {"raw.gz": hashlib.md5(raw_bytes).hexdigest()}), patch.object(build, "FEATURE_SOURCES", {"pfam": "pfam.rds"}):
                result = build.validate_source_inputs(root, preparation)
                self.assertEqual(result["pfam.rds"]["verification_scope"], "integrity_against_preparation_receipt")
                feature.write_bytes(b"changed")
                with self.assertRaisesRegex(build.BuildError, "Checksum mismatch"):
                    build.validate_source_inputs(root, preparation)
                feature.write_bytes(feature_bytes)
                preparation["feature_sources"]["pfam"]["size"] += 1
                with self.assertRaisesRegex(build.BuildError, "file-size mismatch"):
                    build.validate_source_inputs(root, preparation)
                feature.unlink()
                with self.assertRaisesRegex(build.BuildError, "Missing annotation inputs"):
                    build.validate_source_inputs(root, preparation)


if __name__ == "__main__":
    unittest.main()
