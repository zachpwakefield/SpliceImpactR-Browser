from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from backend.app.errors import StartupValidationError
from backend.app.ppi_context import (
    CONTEXT_KIND, EXPORT_SCHEMA, PUBLIC_PPI_RDS_SHA256, SOURCE_NAME,
    canonical_json, file_sha256, load_optional_ppi_context, validate_input_record,
)
from backend.builder.ppi_context import build_ppi_context
from backend.datasets import get_dataset_profile


FOCAL = "ENSG00000185591"
PARTNER = "ENSG00000000002"
UNKNOWN = "ENSG00000000003"


def source_rows() -> list[dict]:
    plain = {"geneA": FOCAL, "geneB": PARTNER, "biogrid": True, "ddi": False, "dmi": False,
             "ddiA": [], "ddiB": [], "dmiA": [], "dmiB": []}
    forward = {**plain, "ddi": True, "ddiA": ["PF00001"], "ddiB": ["PF00002"]}
    reverse = {**plain, "geneA": UNKNOWN, "geneB": FOCAL, "dmi": True,
               "dmiA": ["LIG_TEST-with-hyphen", "SM00028"], "dmiB": ["PF00003", "IPR00001"]}
    self_record = {**plain, "geneB": FOCAL, "ddi": True, "dmi": True,
                   "ddiA": ["PF00001"], "ddiB": ["PF00004"], "dmiA": ["LIG_SELF"], "dmiB": ["PF00004"]}
    # Synthetic duplicate evidence is intentionally retained as a record, not
    # presented as an extra unique interaction or silently collapsed.
    return [forward, reverse, self_record, plain, copy.deepcopy(forward)]


def write_export(directory: Path, package, rows: list[dict] | None = None) -> dict:
    directory.mkdir(parents=True)
    rows = source_rows() if rows is None else rows
    stream = directory / "interactions.ndjson"
    stream.write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows))
    profile = package.profile
    receipt = {
        "schema": EXPORT_SCHEMA, "kind": CONTEXT_KIND, "source": SOURCE_NAME,
        "dataset_id": profile.dataset_id, "species": profile["species"],
        "gencode_release": profile["gencode_release"], "ensembl_release": profile["ensembl_release"],
        "assembly": profile["assembly"], "annotation_build_hash": package.build_hash,
        "package": "SpliceImpactR", "package_version": "1.0.0", "source_rds_sha256": PUBLIC_PPI_RDS_SHA256,
        "input_file": stream.name, "input_sha256": file_sha256(stream), "records": len(rows),
        "unique_genes": len({row[key] for row in rows for key in ("geneA", "geneB")}),
        "network_annotation_release_matched": False,
    }
    (directory / "context_manifest.json").write_bytes(canonical_json(receipt))
    return receipt


class PpiContextBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        profile = get_dataset_profile("human-gencode-v45")
        package_root = self.root / "data" / "builds" / profile["package_dir"]
        package_root.mkdir(parents=True)
        # Minimal standalone source-contract fixture, not a full annotation
        # acceptance package. The production CLI loads RuntimePackage first.
        self.package = SimpleNamespace(profile=profile, dataset_id=profile.dataset_id,
                                       build_hash="ppi-test-annotation-build", root=package_root)
        self.source = self.root / "export"
        self.output = self.root / "data" / "ppi_context" / profile.dataset_id
        self.receipt = write_export(self.source, self.package)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def update_receipt(self, **updates) -> None:
        self.receipt.update(updates)
        (self.source / "context_manifest.json").write_bytes(canonical_json(self.receipt))

    def test_streamed_sidecar_loads_with_exact_identity_and_preserves_base_files(self) -> None:
        base_manifest = self.package.root / "manifest.json"
        base_manifest.write_text('{"sentinel":"unchanged"}')
        base_database = self.package.root / "annotation.sqlite"
        base_database.write_bytes(b"unchanged base fixture")
        before = (base_manifest.read_bytes(), base_database.read_bytes())
        metadata = build_ppi_context(self.source, self.package, self.output)
        context = load_optional_ppi_context(self.root, self.package.profile, self.package.build_hash, full_integrity=True)
        self.assertTrue(context.available, context.reason)
        self.assertEqual(context.status, "loaded")
        self.assertEqual(metadata["records"], 5)
        self.assertEqual(metadata["counts"]["self_records"], 1)
        self.assertEqual(context.database.fetch_one("SELECT COUNT(*) AS count FROM gene_record")["count"], 9)
        self.assertEqual((base_manifest.read_bytes(), base_database.read_bytes()), before)
        self.assertIsNone(context.provenance()["resourceRelease"])
        self.assertIsNone(context.provenance()["resourceDate"])
        self.assertFalse(context.provenance()["networkAnnotationReleaseMatched"])
        self.assertFalse(context.api_status()["predictionAvailable"])

    def test_dataset_species_release_build_and_source_hash_mismatches_fail_before_publication(self) -> None:
        for key, invalid in (("dataset_id", "human-gencode-v50"), ("species", "mouse"),
                             ("gencode_release", 50), ("ensembl_release", 116),
                             ("assembly", "GRCh37"), ("annotation_build_hash", "wrong-build"),
                             ("source_rds_sha256", "0" * 64), ("package", "unverified-package"),
                             ("network_annotation_release_matched", True)):
            with self.subTest(key=key):
                original = copy.deepcopy(self.receipt)
                self.update_receipt(**{key: invalid})
                with self.assertRaises(StartupValidationError):
                    build_ppi_context(self.source, self.package, self.output)
                self.assertFalse(self.output.exists())
                self.receipt = original
                self.update_receipt()

    def test_stream_checksum_and_count_mismatches_never_publish_partial_context(self) -> None:
        for updates in ({"input_sha256": "0" * 64}, {"records": 6}, {"records": 4}, {"unique_genes": 99}):
            with self.subTest(updates=updates):
                original = copy.deepcopy(self.receipt)
                self.update_receipt(**updates)
                with self.assertRaises(StartupValidationError):
                    build_ppi_context(self.source, self.package, self.output)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.output.parent.glob(".ppi-context-*")), [])
                self.receipt = original
                self.update_receipt()

    def test_malformed_gene_boolean_tokens_and_flag_set_contradictions_are_rejected(self) -> None:
        baseline = source_rows()[0]
        invalid_rows = [
            {**baseline, "geneA": "ENSMUSG00000000001"},
            {**baseline, "geneB": FOCAL + ".1"},
            {**baseline, "geneB": "ENSG" + "1" * 500},
            {**baseline, "biogrid": 1},
            {**baseline, "ddiA": "PF00001"},
            {**baseline, "ddiA": [None]},
            {**baseline, "ddiA": []},
            {**baseline, "ddi": False},
            {**baseline, "dmi": True},
            {**baseline, "confidence": 0.9},
        ]
        for row in invalid_rows:
            with self.subTest(row=row), self.assertRaises(StartupValidationError):
                validate_input_record(row)
        # Unsupported but genuine endpoint tokens are retained, not relabeled
        # as Pfam or silently discarded to manufacture support.
        self.assertEqual(validate_input_record(source_rows()[1])["dmiA"], ["LIG_TEST-with-hyphen", "SM00028"])

    def test_existing_sidecar_and_annotation_directory_are_never_overwritten(self) -> None:
        build_ppi_context(self.source, self.package, self.output)
        before = file_sha256(self.output / "context.sqlite")
        with self.assertRaisesRegex(StartupValidationError, "already exists"):
            build_ppi_context(self.source, self.package, self.output)
        self.assertEqual(file_sha256(self.output / "context.sqlite"), before)
        with self.assertRaisesRegex(StartupValidationError, "separate"):
            build_ppi_context(self.source, self.package, self.package.root / "new-context")

    def test_missing_human_and_mouse_statuses_are_not_false_zero_evidence(self) -> None:
        missing = load_optional_ppi_context(self.root, self.package.profile, self.package.build_hash)
        self.assertEqual(missing.status, "unavailable")
        self.assertIsNone(missing.api_status()["sourceRecords"])
        mouse_profile = get_dataset_profile("mouse-gencode-m39")
        mouse = load_optional_ppi_context(self.root, mouse_profile, "mouse-build")
        self.assertEqual(mouse.status, "not_applicable")
        self.assertFalse(mouse.available)
        mouse_package = SimpleNamespace(profile=mouse_profile, root=self.package.root, build_hash="mouse-build")
        with self.assertRaisesRegex(StartupValidationError, "human-only"):
            build_ppi_context(self.source, mouse_package, self.root / "mouse-sidecar")

    def test_runtime_rejects_wrong_build_tampering_and_journals(self) -> None:
        build_ppi_context(self.source, self.package, self.output)
        mismatch = load_optional_ppi_context(self.root, self.package.profile, "another-build")
        self.assertEqual(mismatch.status, "unavailable")
        self.assertIn("another annotation build", mismatch.reason)
        journal = self.output / "context.sqlite-wal"
        journal.write_bytes(b"unexpected mutable state")
        self.assertFalse(load_optional_ppi_context(self.root, self.package.profile, self.package.build_hash).available)
        journal.unlink()
        database = self.output / "context.sqlite"
        database.write_bytes(database.read_bytes() + b"tampered")
        self.assertIn("checksum", load_optional_ppi_context(self.root, self.package.profile, self.package.build_hash).reason)

    def test_source_symlink_and_context_symlink_are_rejected(self) -> None:
        stream = self.source / "interactions.ndjson"
        renamed = self.source / "actual.ndjson"
        stream.rename(renamed)
        stream.symlink_to(renamed)
        with self.assertRaisesRegex(StartupValidationError, "regular internal"):
            build_ppi_context(self.source, self.package, self.output)
        stream.unlink()
        renamed.rename(stream)
        build_ppi_context(self.source, self.package, self.output)
        manifest = self.output / "manifest.json"
        actual_manifest = self.output / "actual-manifest.json"
        manifest.rename(actual_manifest)
        manifest.symlink_to(actual_manifest)
        rejected = load_optional_ppi_context(self.root, self.package.profile, self.package.build_hash)
        self.assertEqual(rejected.status, "unavailable")
        self.assertIn("regular internal", rejected.reason)


if __name__ == "__main__":
    unittest.main()
