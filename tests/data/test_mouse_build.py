from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from backend.builder.constants import ANNOTATION_POLICY, FEATURE_SOURCES
from backend.builder.schema import canonical_table_hashes
from backend.datasets import get_dataset_profile


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "data" / "builds" / "mouse_gencode_m34"
# Independently streamed from the checksum-verified, complete official M34 GTF.
INVENTORY_SHA256 = "18c0fbabc0592642846a01633c2d4ad3fccc3cdcf52b32924c429393e0c25621"
TSL_COUNTS = {"1": 43553, "2": 13836, "3": 18266, "4": 3, "5": 23765, "unscored": 49653}
SP1_TRANSCRIPTS = {
    "ENSMUST00000170884.8", "ENSMUST00000163709.8", "ENSMUST00000001326.7",
    "ENSMUST00000165837.8", "ENSMUST00000169619.2", "ENSMUST00000168802.2",
}


class MouseM34BuildAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database = BUILD / "annotation.sqlite"
        if not database.is_file():
            raise unittest.SkipTest("Full mouse M34 package has not been built")
        cls.connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
        cls.connection.row_factory = sqlite3.Row
        cls.manifest = json.loads((BUILD / "manifest.json").read_text())
        cls.report = json.loads((BUILD / "validation_report.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "connection"):
            cls.connection.close()

    def test_full_identity_source_inventory_and_validation_gate(self) -> None:
        profile = get_dataset_profile("mouse-gencode-m34")
        for key, expected in (("dataset_id", profile.dataset_id), ("species", "mouse"),
                              ("gencode_release", "M34"), ("ensembl_release", 111),
                              ("assembly", "GRCm39"), ("scope", "full")):
            self.assertEqual(self.manifest[key], expected)
        self.assertFalse(self.manifest["technical_preview"])
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["errors"], [])
        self.assertEqual(self.manifest["build_hash"], self.report["build_hash"])
        self.assertEqual(self.manifest["counts"]["gene"], 57126)
        self.assertEqual(self.manifest["counts"]["transcript"], 149076)
        self.assertEqual(self.manifest["counts"]["exon"], 863151)
        self.assertEqual(self.report["gtf"]["selected_feature_rows"], dict(profile["expected"]["gtf_feature_rows"]))
        self.assertEqual(self.report["fasta"], {"transcript_records_selected": 66254, "protein_records_selected": 66254})
        preparation = self.report["feature_preparation"]
        self.assertEqual(preparation["annotation_policy"], ANNOTATION_POLICY)
        self.assertEqual(preparation["annotation_inventory"]["transcript_ids_sha256"], INVENTORY_SHA256)
        ids = [row[0] for row in self.connection.execute("SELECT transcript_id FROM transcript ORDER BY transcript_id")]
        self.assertTrue(all(identifier.startswith("ENSMUST") for identifier in ids))
        self.assertEqual(hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest(), INVENTORY_SHA256)

    def test_all_support_levels_and_gene_checkpoint_isoforms_are_retained(self) -> None:
        observed = dict(self.connection.execute("SELECT CASE WHEN tsl IS NULL OR tsl='NA' THEN 'unscored' ELSE SUBSTR(tsl,1,1) END,COUNT(*) FROM transcript GROUP BY 1"))
        self.assertEqual(observed, TSL_COUNTS)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM transcript WHERE tsl='NA'").fetchone()[0], 24122)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM transcript WHERE tsl IS NULL").fetchone()[0], 25531)
        sp1 = {row[0] for row in self.connection.execute("SELECT transcript_id_versioned FROM transcript JOIN gene USING(gene_id) WHERE gene.symbol='Sp1'")}
        self.assertEqual(sp1, SP1_TRANSCRIPTS)
        for symbol, expected in (("Tpm1", 21), ("Fgfr3", 17)):
            self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM transcript JOIN gene USING(gene_id) WHERE gene.symbol=?", (symbol,)).fetchone()[0], expected)

    def test_release_pinned_feature_receipts_and_explicit_availability(self) -> None:
        preparation = self.report["feature_preparation"]
        self.assertEqual(preparation["biomart"], dict(get_dataset_profile("mouse-gencode-m34")["biomart"]))
        self.assertEqual(self.report["features"]["orphan_row_count"], 0)
        self.assertEqual(self.report["features"]["invalid_row_count"], 0)
        for source in FEATURE_SOURCES:
            receipt = preparation["feature_sources"][source]
            self.assertIn(receipt["status"], {"available", "available-empty", "unavailable"})
            exported = self.report["feature_export"]["sources"][source]
            self.assertEqual((exported["rows"], exported["distinct_transcripts"], exported["distinct_feature_ids"]),
                             (receipt["rows"], receipt["distinct_transcripts"], receipt["distinct_feature_ids"]))
            if receipt["status"] == "unavailable":
                self.assertTrue(receipt["reason"])
                self.assertEqual(receipt["rows"], 0)
        self.assertGreater(self.manifest["counts"]["protein_feature"], 0)

    def test_only_exact_translation_maps_have_complete_feature_projection(self) -> None:
        wrong = self.connection.execute(
            "SELECT COUNT(*) FROM protein_feature_segment AS segment "
            "JOIN protein_feature AS feature USING(feature_id) "
            "LEFT JOIN translation_mapping AS mapping USING(transcript_id) "
            "WHERE COALESCE(mapping.status,'missing') <> 'exact'"
        ).fetchone()[0]
        self.assertEqual(wrong, 0)
        wrong = self.connection.execute(
            "SELECT COUNT(*) FROM (SELECT feature.feature_id FROM protein_feature AS feature "
            "JOIN translation_mapping AS mapping USING(transcript_id) "
            "LEFT JOIN protein_feature_segment AS segment USING(feature_id) "
            "WHERE mapping.status='exact' GROUP BY feature.feature_id "
            "HAVING COALESCE(SUM(segment.nt_end0-segment.nt_start0),0) "
            "<>3*(feature.aa_end1-feature.aa_start1+1))"
        ).fetchone()[0]
        self.assertEqual(wrong, 0)
        self.assertGreater(self.report["translation_mapping_statuses"].get("exact", 0), 0)

    def test_sqlite_integrity_and_canonical_content_hashes(self) -> None:
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(canonical_table_hashes(self.connection), self.manifest["content_hashes"])


if __name__ == "__main__":
    unittest.main()
