from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import copy
import io
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts import smoke_test_api as smoke


DATASET = "mouse-gencode-m39"
GENE = "ENSMUSG00000012345"
TRANSCRIPT = "ENSMUST00000054321"


def manifest() -> dict:
    return {
        "datasetId": DATASET, "buildHash": "mouse-fixture-build", "species": "mouse",
        "assembly": "GRCm39", "gencodeRelease": "M39", "ensemblRelease": 116,
        "release": "GENCODE M39", "scope": "full", "capabilities": {},
    }


def gene() -> dict:
    return {
        "id": GENE, "chr": "chr12", "start0": 100, "end0": 900,
        "transcripts": [
            {"id": "ENSMUST00000000001", "geneId": GENE, "proteinLength": 0},
            {"id": TRANSCRIPT, "versionedId": TRANSCRIPT + ".2", "geneId": GENE, "proteinLength": 88},
        ],
    }


class SmokeApiToolTests(unittest.TestCase):
    def test_scope_appends_to_plain_existing_and_empty_queries_without_losing_values(self) -> None:
        for path in ("/api/v1/manifest", "/api/v1/search?q=Sp1&limit=50",
                     "/api/v1/transcripts/x/features?sources=interpro%2Cpfam&empty="):
            with self.subTest(path=path):
                scoped = smoke._dataset_path(path, DATASET)
                original = parse_qs(urlsplit(path).query, keep_blank_values=True)
                actual = parse_qs(urlsplit(scoped).query, keep_blank_values=True)
                self.assertEqual(actual.pop("dataset"), [DATASET])
                self.assertEqual(actual, original)
                self.assertEqual(urlsplit(scoped).path, urlsplit(path).path)
        self.assertEqual(smoke._dataset_path("/api/v1/manifest?", None), "/api/v1/manifest?")

    def test_existing_matching_scope_is_not_duplicated_and_conflicting_or_duplicate_scopes_fail(self) -> None:
        matching = "/api/v1/manifest?dataset=" + DATASET
        self.assertEqual(smoke._dataset_path(matching, DATASET), matching)
        for path in ("/api/v1/manifest?dataset=human-gencode-v45", matching + "&dataset=" + DATASET):
            with self.subTest(path=path), self.assertRaisesRegex(smoke.SmokeFailure, "conflicting or duplicate"):
                smoke._dataset_path(path, DATASET)

    def test_invalid_dataset_identifier_cannot_modify_the_query(self) -> None:
        for invalid in ("", "unsafe ID", "mouse&dataset=human", "x" * 81):
            with self.subTest(dataset=invalid), self.assertRaisesRegex(smoke.SmokeFailure, "safe nonempty"):
                smoke._dataset_path("/api/v1/health", invalid)

    def test_first_translation_comes_from_the_selected_gene_and_retains_mouse_identity(self) -> None:
        self.assertEqual(smoke._select_transcript(gene(), None), TRANSCRIPT)

    def test_explicit_base_and_exact_versioned_transcripts_are_resolved_within_the_gene(self) -> None:
        for requested in (TRANSCRIPT, TRANSCRIPT + ".2", TRANSCRIPT.lower()):
            self.assertEqual(smoke._select_transcript(gene(), requested), TRANSCRIPT)
        for requested in ("ENST00000327443", TRANSCRIPT + ".99", ""):
            with self.subTest(requested=requested), self.assertRaises(smoke.SmokeFailure):
                smoke._select_transcript(gene(), requested)

    def test_nontranslated_selection_and_genes_without_translation_fail_with_actionable_errors(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "no translated protein"):
            smoke._select_transcript(gene(), "ENSMUST00000000001")
        unavailable = gene()
        unavailable["transcripts"][1]["proteinLength"] = None
        with self.assertRaisesRegex(smoke.SmokeFailure, "choose another gene"):
            smoke._select_transcript(unavailable, None)

    def test_malformed_or_wrong_gene_transcript_rows_are_rejected(self) -> None:
        malformed = gene()
        malformed["transcripts"].append("not a transcript")
        with self.assertRaisesRegex(smoke.SmokeFailure, "inventory is malformed"):
            smoke._select_transcript(malformed, None)
        mismatched = gene()
        mismatched["transcripts"][1]["geneId"] = "ENSMUSG99999999999"
        with self.assertRaisesRegex(smoke.SmokeFailure, "owned by another gene"):
            smoke._select_transcript(mismatched, None)

    def test_exact_gene_symbol_wins_prefix_results_and_ambiguous_symbols_fail(self) -> None:
        exact = {"kind": "gene", "id": GENE, "symbol": "Sp1"}
        prefix = {"kind": "gene", "id": "ENSMUSG99999999999", "symbol": "Sp10"}
        self.assertEqual(smoke._select_gene([prefix, exact], "SP1"), exact)
        with self.assertRaisesRegex(smoke.SmokeFailure, "unambiguous gene"):
            smoke._select_gene([exact, {**exact, "id": "ENSMUSG99999999999"}], "SP1")

    def test_requested_manifest_catalog_and_health_identities_agree(self) -> None:
        current = manifest()
        health = {"datasetId": DATASET, "buildHash": current["buildHash"]}
        smoke._validate_dataset_identity(DATASET, {"datasets": [current]}, current, health)
        # A harmless JSON scalar representation difference must not appear to
        # be a release mismatch when both API fields describe release 116.
        smoke._validate_dataset_identity(DATASET, {"datasets": [current]},
                                         {**current, "ensemblRelease": "116"}, health)

    def test_dataset_or_build_identity_mismatch_is_not_silently_accepted(self) -> None:
        current = manifest()
        health = {"datasetId": DATASET, "buildHash": current["buildHash"]}
        cases = [
            ({"datasets": [current]}, {**current, "datasetId": "human-gencode-v45"}, health),
            ({"datasets": [current]}, current, {**health, "datasetId": "human-gencode-v45"}),
            ({"datasets": [current]}, current, {**health, "buildHash": "different-build"}),
            ({"datasets": []}, current, health),
            ({"datasets": [current, current]}, current, health),
        ]
        for catalog, selected, selected_health in cases:
            with self.subTest(catalog=catalog, manifest=selected, health=selected_health), self.assertRaises(smoke.SmokeFailure):
                smoke._validate_dataset_identity(DATASET, catalog, selected, selected_health)

    def test_species_assembly_and_release_catalog_mismatches_are_rejected(self) -> None:
        current = manifest()
        health = {"datasetId": DATASET, "buildHash": current["buildHash"]}
        for key, invalid in (("species", "human"), ("assembly", "GRCh38.p14"),
                             ("gencodeRelease", 45), ("ensemblRelease", 111), ("buildHash", "wrong-build")):
            with self.subTest(key=key), self.assertRaisesRegex(smoke.SmokeFailure, key):
                smoke._validate_dataset_identity(DATASET, {"datasets": [{**current, key: invalid}]}, current, health)

    def fake_api(self, responses: dict[str, dict], requests: list[str]):
        def get(_base_url: str, path: str):
            requests.append(path)
            split = urlsplit(path)
            if split.path not in responses:
                raise AssertionError("Unexpected API request: " + path)
            return 200, copy.deepcopy(responses[split.path])
        return get

    def responses(self) -> dict[str, dict]:
        current = manifest()
        return {
            "/api/v1/health": {"status": "ok", "readOnly": True,
                               "datasetId": DATASET, "buildHash": current["buildHash"]},
            "/api/v1/manifest": current,
            "/api/v1/datasets": {"defaultDatasetId": "human-gencode-v45", "datasets": [current]},
            "/api/v1/search": {"results": [
                {"kind": "transcript", "id": "ENST00000327443", "geneId": "ENSG00000185591"},
                {"kind": "gene", "id": GENE, "symbol": "Sp1"},
            ]},
            "/api/v1/genes/" + GENE: gene(),
            "/api/v1/region": {"genes": [{"id": GENE}], "transcripts": [{"id": TRANSCRIPT}]},
            "/api/v1/transcripts/" + TRANSCRIPT: {"id": TRANSCRIPT, "geneId": GENE},
            "/api/v1/transcripts/" + TRANSCRIPT + "/features": {"transcriptId": TRANSCRIPT, "features": [], "mapping": {}},
            "/api/v1/transcripts/" + TRANSCRIPT + "/sequence": {"kind": "protein", "available": True, "length": 88},
        }

    def args(self, **overrides) -> argparse.Namespace:
        return argparse.Namespace(**{
            "base_url": "http://127.0.0.1:8000", "dataset": DATASET, "gene_query": "SP1",
            "transcript": None, "feature_sources": "interpro,pfam", "expect_scope": "full", **overrides,
        })

    def test_complete_mock_run_scopes_every_scientific_request_but_leaves_catalog_global(self) -> None:
        requests = []
        output = io.StringIO()
        with patch.object(smoke, "_get", self.fake_api(self.responses(), requests)), redirect_stdout(output):
            smoke.run(self.args())
        self.assertIn("API smoke test passed", output.getvalue())
        self.assertIn(TRANSCRIPT, output.getvalue())
        self.assertEqual(len(requests), 9)
        for path in requests:
            if urlsplit(path).path == "/api/v1/datasets":
                self.assertEqual(path, "/api/v1/datasets")
            else:
                self.assertEqual(parse_qs(urlsplit(path).query).get("dataset"), [DATASET])

    def test_legacy_unscoped_run_still_selects_a_real_gene_translation_without_catalog_dependency(self) -> None:
        requests = []
        with patch.object(smoke, "_get", self.fake_api(self.responses(), requests)), redirect_stdout(io.StringIO()):
            smoke.run(self.args(dataset=None))
        self.assertEqual(len(requests), 8)
        self.assertTrue(all("dataset" not in parse_qs(urlsplit(path).query) for path in requests))

    def test_transcript_detail_ownership_mismatch_fails_even_if_gene_inventory_was_valid(self) -> None:
        responses = self.responses()
        responses["/api/v1/transcripts/" + TRANSCRIPT]["geneId"] = "ENSMUSG99999999999"
        with patch.object(smoke, "_get", self.fake_api(responses, [])), redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(smoke.SmokeFailure, "owned by another gene"):
            smoke.run(self.args())


if __name__ == "__main__":
    unittest.main()
