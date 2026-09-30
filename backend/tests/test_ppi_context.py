from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.package import load_runtime_package
from backend.app.ppi_context import file_sha256
from backend.builder.ppi_context import build_ppi_context
from backend.tests.test_datasets import synthetic_dataset
from tests.data.test_ppi_context_build import FOCAL, PARTNER, UNKNOWN, source_rows, write_export


class PpiContextApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.packages = {dataset: synthetic_dataset(self.root, dataset) for dataset in
                         ("human-gencode-v45", "human-gencode-v50", "mouse-gencode-m39")}
        package_path = self.packages["human-gencode-v45"]
        connection = sqlite3.connect(package_path / "annotation.sqlite")
        connection.execute(
            "INSERT INTO gene(gene_id,gene_id_versioned,symbol,biotype,contig,start0,end0,strand,bin) "
            "VALUES(?,?,?,?,?,?,?,?,?)", (PARTNER, PARTNER + ".1", "PARTNER", "protein_coding", "chr12", 1, 100, "+", 4681),
        )
        connection.execute("INSERT INTO gene(gene_id,gene_id_versioned,symbol,biotype,contig,start0,end0,strand,bin) "
                           "VALUES('ENSG00000000099','ENSG00000000099.1','ZERO','protein_coding','chr12',100,200,'+',4681)")
        connection.commit()
        connection.close()
        self.package = load_runtime_package(package_path, dev_fixture=False)
        self.source = self.root / "export"
        write_export(self.source, self.package)
        self.context_root = self.root / "data" / "ppi_context" / self.package.dataset_id
        build_ppi_context(self.source, self.package, self.context_root)
        self.app = create_app(project_root=self.root)
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def endpoint(self, **params):
        return self.client.get(f"/api/v1/genes/{FOCAL}/ppi-context", params={"dataset": self.package.dataset_id, **params})

    def test_catalog_and_manifest_expose_only_validated_context_and_never_predictions(self) -> None:
        manifest = self.client.get("/api/v1/manifest?dataset=human-gencode-v45").json()
        self.assertTrue(manifest["capabilities"]["ppiContext"])
        self.assertFalse(manifest["capabilities"]["ppiPredictions"])
        self.assertEqual(manifest["ppiContext"]["status"], "loaded")
        self.assertFalse(manifest["ppiContext"]["predictionAvailable"])
        catalog = self.client.get("/api/v1/datasets").json()
        states = {row["datasetId"]: row["ppiContext"]["status"] for row in catalog["datasets"]}
        self.assertEqual(states, {"human-gencode-v45": "loaded", "human-gencode-v50": "unavailable", "mouse-gencode-m39": "not_applicable"})

    def test_shared_frontend_fixture_matches_the_actual_bounded_api_response(self) -> None:
        path = Path(__file__).resolve().parents[2] / "tests" / "data" / "fixtures" / "ppi-context-api.example.json"
        self.assertEqual(self.endpoint(limit=3).json(), json.loads(path.read_text(encoding="utf-8")))

    def test_feature_linked_and_all_counts_are_record_counts_not_unique_interactions(self) -> None:
        response = self.endpoint()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "loaded")
        self.assertEqual(payload["counts"], {"records": 4, "allRecords": 5, "partnerGenes": 3,
                                            "biogridRecords": 4, "ddiRecords": 3, "dmiRecords": 2})
        self.assertEqual(payload["page"]["evidence"], "feature-linked")
        all_records = self.endpoint(evidence="all").json()
        self.assertEqual(all_records["counts"]["records"], 5)
        self.assertEqual([record["recordId"].split(":")[-1] for record in all_records["records"]], ["1", "2", "3", "4", "5"])
        self.assertFalse(payload["predictionAvailable"])
        self.assertIsNone(payload["provenance"]["resourceRelease"])
        self.assertFalse(payload["provenance"]["originalTokenPairingsAvailable"])

    def test_forward_reverse_and_self_endpoint_owners_preserve_raw_and_selected_tokens(self) -> None:
        records = self.endpoint().json()["records"]
        forward, reverse, self_record = records[:3]
        self.assertEqual((forward["geneA"], forward["geneB"], forward["focalEndpoint"]), (FOCAL, PARTNER, "A"))
        self.assertEqual(forward["ddi"]["focalPfamAccessions"], ["PF00001"])
        self.assertEqual(forward["ddi"]["partnerPfamAccessions"], ["PF00002"])
        self.assertEqual(forward["partner"], {"id": PARTNER, "symbol": "PARTNER", "availableInDataset": True})
        self.assertEqual((reverse["geneA"], reverse["geneB"], reverse["focalEndpoint"]), (UNKNOWN, FOCAL, "B"))
        self.assertEqual(reverse["dmi"]["focalTokens"], ["PF00003", "IPR00001"])
        self.assertEqual(reverse["dmi"]["partnerTokens"], ["LIG_TEST-with-hyphen", "SM00028"])
        self.assertEqual(reverse["partner"], {"id": UNKNOWN, "symbol": UNKNOWN, "availableInDataset": False})
        self.assertTrue(self_record["selfInteraction"])
        self.assertEqual(self_record["focalEndpoint"], "A+B")
        self.assertEqual(self_record["ddi"]["focalPfamAccessions"], ["PF00001", "PF00004"])
        self.assertEqual(self_record["sourceEndpoints"]["ddiA"], ["PF00001"])
        self.assertEqual(self_record["sourceEndpoints"]["ddiB"], ["PF00004"])

    def test_pagination_is_deterministic_bounded_and_does_not_hardcode_human_isoforms(self) -> None:
        first = self.endpoint(limit=1).json()
        second = self.endpoint(limit=1, offset=first["page"]["nextOffset"]).json()
        self.assertEqual(first["page"], {"evidence": "feature-linked", "offset": 0, "limit": 1,
                                          "returned": 1, "hasMore": True, "nextOffset": 1})
        self.assertNotEqual(first["records"][0]["recordId"], second["records"][0]["recordId"])
        beyond = self.endpoint(limit=100, offset=100).json()
        self.assertEqual(beyond["records"], [])
        self.assertFalse(beyond["page"]["hasMore"])
        for params in ({"limit": 101}, {"limit": 0}, {"offset": -1}):
            self.assertEqual(self.endpoint(**params).status_code, 422)
        self.assertEqual(self.endpoint(evidence="prediction").status_code, 400)

    def test_zero_records_missing_context_and_mouse_not_applicable_remain_distinct(self) -> None:
        # PARTNER has source records, while this synthetic annotation gene has
        # no network records; a loaded zero remains genuine evidence coverage.
        zero = self.client.get("/api/v1/genes/ENSG00000000099/ppi-context?dataset=human-gencode-v45").json()
        self.assertEqual(zero["status"], "loaded")
        self.assertEqual(zero["counts"]["records"], 0)
        other_human = self.client.get(f"/api/v1/genes/{FOCAL}/ppi-context?dataset=human-gencode-v50").json()
        self.assertEqual(other_human["status"], "unavailable")
        self.assertIsNone(other_human["counts"])
        mouse = self.client.get("/api/v1/genes/ENSMUSG00000185591/ppi-context?dataset=mouse-gencode-m39").json()
        self.assertEqual(mouse["status"], "not_applicable")
        self.assertIsNone(mouse["counts"])

    def test_missing_foreign_and_ambiguous_dataset_entities_fail_without_fallback(self) -> None:
        for url, expected in (
            (f"/api/v1/genes/{FOCAL}/ppi-context?dataset=mouse-gencode-m39", 404),
            (f"/api/v1/genes/{FOCAL}/ppi-context?dataset=unknown", 400),
            (f"/api/v1/genes/{FOCAL}/ppi-context?dataset=human-gencode-v45&dataset=human-gencode-v50", 400),
            ("/api/v1/genes/ENST00000327443/ppi-context?dataset=human-gencode-v45", 404),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, expected)

    def test_requests_and_sidecar_queries_are_read_only_with_context_aware_etags(self) -> None:
        context = self.app.state.dataset_contexts[self.package.dataset_id].package.ppi_context
        paths = [self.package.root / "manifest.json", self.package.database.path,
                 context.root / "manifest.json", context.database.path]
        before = [file_sha256(path) for path in paths]
        response = self.endpoint()
        cached = self.client.get(response.request.url, headers={"If-None-Match": response.headers["etag"]})
        self.assertEqual(cached.status_code, 304)
        with context.database.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM interaction_record")
        self.assertEqual([file_sha256(path) for path in paths], before)
        self.assertEqual(response.headers["x-transcript-browser-dataset"], self.package.dataset_id)


if __name__ == "__main__":
    unittest.main()
