from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from backend.builder.constants import (
    ANNOTATION_POLICY, ASSEMBLY, EXPECTED_GTF_FEATURE_ROWS, FEATURE_COLUMNS,
    FEATURE_QUERY_POLICY, FEATURE_SOURCES, PREPARATION_MANIFEST, PREPARATION_SCHEMA, REQUIRED_INPUTS,
)
from backend.builder.source_manifest import read_preparation_manifest, transcript_inventory_digest


def manifest_fixture() -> dict:
    return {
        "schema": PREPARATION_SCHEMA, "gencode_release": 45, "ensembl_release": 111,
        "assembly": ASSEMBLY, "annotation_policy": copy.deepcopy(ANNOTATION_POLICY),
        "feature_query_policy": copy.deepcopy(FEATURE_QUERY_POLICY),
        "annotation_inventory": {"genes": EXPECTED_GTF_FEATURE_ROWS["gene"],
            "transcripts": EXPECTED_GTF_FEATURE_ROWS["transcript"], "transcript_ids_sha256": "a" * 64},
        "producer": {"package": "SpliceImpactR", "version": "1.0.0"},
        "required_feature_columns": list(FEATURE_COLUMNS),
        "raw_inputs": {name: {"file": name, "md5": md5, "size": 10} for name, md5 in REQUIRED_INPUTS.items()},
        "feature_sources": {name: {"file": filename, "sha256": "b" * 64, "size": 10,
            "rows": 2, "distinct_transcripts": 1, "distinct_feature_ids": 1} for name, filename in FEATURE_SOURCES.items()},
    }


class PreparationManifestTests(unittest.TestCase):
    def load(self, manifest: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / PREPARATION_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
            return read_preparation_manifest(source)

    def test_fresh_feature_counts_and_digests_are_accepted(self) -> None:
        manifest = manifest_fixture()
        manifest["feature_sources"]["interpro"].update(rows=900000, distinct_transcripts=100000, sha256="c" * 64)
        self.assertEqual(self.load(manifest), manifest)

    def test_filtered_or_incomplete_inventory_is_rejected(self) -> None:
        for mutation in ("tsl", "biotype", "incomplete", "inventory", "query_biotype", "test_fixture"):
            with self.subTest(mutation=mutation):
                manifest = manifest_fixture()
                if mutation == "tsl": manifest["annotation_policy"]["transcript_support_level_filter"] = ["1", "2", "3"]
                elif mutation == "biotype": manifest["annotation_policy"]["transcript_biotype_filter"] = "protein_coding"
                elif mutation == "incomplete": manifest["annotation_policy"]["exclude_incomplete_cds"] = True
                elif mutation == "inventory": manifest["annotation_inventory"]["transcripts"] -= 1
                elif mutation == "query_biotype": manifest["feature_query_policy"]["biomart_transcript_biotype_filter"] = "protein_coding"
                else: manifest["feature_query_policy"]["test_fixture"] = True
                with self.assertRaises(ValueError): self.load(manifest)

    def test_wrong_release_missing_source_and_path_injection_are_rejected(self) -> None:
        for mutation in ("release", "source", "filename", "digest", "count", "legacy"):
            with self.subTest(mutation=mutation):
                manifest = manifest_fixture()
                if mutation == "release": manifest["ensembl_release"] = 115
                elif mutation == "source": del manifest["feature_sources"]["elm"]
                elif mutation == "filename": manifest["feature_sources"]["pfam"]["file"] = "../pfam.rds"
                elif mutation == "digest": manifest["feature_sources"]["pfam"]["sha256"] = "invalid"
                elif mutation == "count": manifest["feature_sources"]["pfam"]["rows"] = -1
                else: manifest["schema"] = "transcript-browser-spliceimpactr-cache/v1"
                with self.assertRaises(ValueError): self.load(manifest)

    def test_inventory_hash_is_stable_and_sensitive_to_omitted_models(self) -> None:
        self.assertEqual(transcript_inventory_digest(["T2", "T1"]), transcript_inventory_digest(["T1", "T2"]))
        self.assertNotEqual(transcript_inventory_digest(["T1", "T2"]), transcript_inventory_digest(["T1"]))


if __name__ == "__main__": unittest.main()
