from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.app.errors import StartupValidationError
from backend.app.main import create_app
from backend.app.package import load_runtime_package
from backend.app.package import _load_reference
from backend.app.repository import base_stable_id
from backend.datasets import dataset_profiles, get_dataset_profile, profile_for_metadata
from backend.tests.test_api import make_package, write_db, write_manifest


def synthetic_dataset(root: Path, dataset_id: str) -> Path:
    """Small API contract fixture, not a biological full-build acceptance test."""

    profile = get_dataset_profile(dataset_id)
    package = root / "data" / "builds" / profile["package_dir"]
    package.mkdir(parents=True)
    write_db(package / "annotation.sqlite", technical_preview=False)
    write_manifest(package, technical_preview=False)
    connection = sqlite3.connect(package / "annotation.sqlite")
    if profile["species"] == "mouse":
        for table, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%fts%'").fetchall():
            for column in connection.execute(f'PRAGMA table_info("{table}")').fetchall():
                if column[2] == "TEXT":
                    for before, after in (("ENSG", "ENSMUSG"), ("ENST", "ENSMUST"), ("ENSP", "ENSMUSP"), ("ENSE", "ENSMUSE")):
                        connection.execute(f'UPDATE "{table}" SET "{column[1]}" = replace("{column[1]}", ?, ?)', (before, after))
        connection.execute("UPDATE gene SET symbol='Sp1'")
        connection.execute("UPDATE contig SET length=? WHERE name='chr12'", (profile.contigs["chr12"],))
    if dataset_id == "human-gencode-v50":
        connection.execute("UPDATE sequence SET sequence=replace(sequence,'M','A')")
    if dataset_id == "mouse-gencode-m34":
        connection.execute("UPDATE sequence SET sequence=replace(sequence,'M','G')")
    identity = {"dataset_id": dataset_id, "species": profile["species"], "gencode_release": profile["gencode_release"], "release": profile.release_label, "ensembl_release": profile["ensembl_release"], "assembly": profile["assembly"], "build_hash": dataset_id + "-fixture-hash"}
    for key, value in identity.items():
        connection.execute("INSERT OR REPLACE INTO build_manifest VALUES(?,?)", (key, json.dumps(value)))
    connection.commit()
    connection.close()
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(identity)
    for table in ("gene", "transcript"):
        manifest["counts"][table] = profile["expected"]["gtf_feature_rows"][table]
    manifest["feature_sources"] = [{"name": "Pfam", "records": 1, "status": "available"}, {"name": "ELM", "records": 0, "status": "unavailable", "reason": "Fixture missing-provider evidence"}]
    manifest_path.write_text(json.dumps(manifest))
    report_path = package / "validation_report.json"
    report = json.loads(report_path.read_text())
    report.update(build_hash=identity["build_hash"], counts=manifest["counts"])
    report_path.write_text(json.dumps(report))
    return package


class DatasetRuntimeTests(unittest.TestCase):
    def test_closed_profiles_and_exact_release_pairings(self) -> None:
        expected = {"human-gencode-v45": ("human", 45, 111, "GRCh38.p14"), "human-gencode-v50": ("human", 50, 116, "GRCh38.p14"), "mouse-gencode-m39": ("mouse", "M39", 116, "GRCm39"), "mouse-gencode-m34": ("mouse", "M34", 111, "GRCm39")}
        self.assertEqual(set(dataset_profiles()), set(expected))
        for identifier, identity in expected.items():
            profile = get_dataset_profile(identifier)
            self.assertEqual(tuple(profile[key] for key in ("species", "gencode_release", "ensembl_release", "assembly")), identity)
            self.assertGreater(profile.contigs["chr12"], 100_000_000)
            self.assertFalse(profile["ppi_predictions"])
            metadata = {"dataset_id": identifier, "species": identity[0], "gencode_release": identity[1], "ensembl_release": identity[2], "assembly": identity[3]}
            self.assertEqual(profile_for_metadata(metadata).dataset_id, identifier)
            for key, invalid in (("species", "rat"), ("ensembl_release", 50), ("assembly", "GRCh37"), ("gencode_release", 44)):
                with self.subTest(dataset=identifier, key=key), self.assertRaises(ValueError):
                    profile_for_metadata({**metadata, key: invalid})
        with self.assertRaises(ValueError):
            get_dataset_profile("human-gencode-v999")
        contradictory = {"dataset_id": "human-gencode-v45", "species": "human", "release": "GENCODE v45", "gencode_release": 50, "ensembl_release": 111, "assembly": "GRCh38.p14"}
        with self.assertRaises(ValueError):
            profile_for_metadata(contradictory)
        contradictory["gencode_release"] = 45
        contradictory["ensemblRelease"] = 116
        with self.assertRaises(ValueError):
            profile_for_metadata(contradictory)
        contradictory.pop("ensemblRelease")
        contradictory["datasetId"] = "human-gencode-v50"
        with self.assertRaises(ValueError):
            profile_for_metadata(contradictory)

    def test_legacy_manifest_is_v45_only_and_mouse_ids_normalize(self) -> None:
        legacy = {"release": "GENCODE v45", "ensembl_release": 111, "assembly": "GRCh38.p14"}
        self.assertEqual(profile_for_metadata(legacy, legacy_v45=True).dataset_id, "human-gencode-v45")
        with self.assertRaises(ValueError):
            profile_for_metadata({**legacy, "release": "GENCODE v50", "ensembl_release": 116}, legacy_v45=True)
        self.assertEqual(base_stable_id("ensmust00000327443.9"), "ENSMUST00000327443")

    def test_m34_and_m39_do_not_cross_load_shared_mouse_transcript_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for identifier in ("mouse-gencode-m34", "mouse-gencode-m39"):
                synthetic_dataset(root, identifier)
            app = create_app(project_root=root, dataset="mouse-gencode-m34")
            client = TestClient(app, base_url="http://127.0.0.1")
            for identifier, release, residue in (("mouse-gencode-m34", 111, "G"), ("mouse-gencode-m39", 116, "M"), ("mouse-gencode-m34", 111, "G")):
                manifest = client.get("/api/v1/manifest", params={"dataset": identifier}).json()
                self.assertEqual(manifest["ensemblRelease"], release)
                self.assertFalse(manifest["capabilities"]["ppiPredictions"])
                response = client.get("/api/v1/transcripts/ENSMUST00000327443/sequence", params={"dataset": identifier})
                self.assertEqual(response.json()["sequence"][0], residue)
                self.assertEqual(response.headers["x-transcript-browser-dataset"], identifier)
                exported = client.get("/api/v1/export", params={"dataset": identifier, "entity": "gene", "id": "ENSMUSG00000185591"}).json()
                self.assertEqual(exported["_provenance"]["ensemblRelease"], release)
                ppi = client.get("/api/v1/genes/ENSMUSG00000185591/ppi-context", params={"dataset": identifier}).json()
                self.assertEqual(ppi["status"], "not_applicable")

    def test_catalog_scoped_api_export_and_independent_tabs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for identifier in dataset_profiles():
                synthetic_dataset(root, identifier)
            app = create_app(project_root=root, dataset="human-gencode-v45")
            client_a = TestClient(app, base_url="http://127.0.0.1")
            client_b = TestClient(app, base_url="http://127.0.0.1")
            catalog = client_a.get("/api/v1/datasets").json()
            self.assertEqual(catalog["defaultDatasetId"], "human-gencode-v45")
            self.assertEqual({row["datasetId"] for row in catalog["datasets"]}, set(dataset_profiles()))
            mouse = client_b.get("/api/v1/manifest?dataset=mouse-gencode-m39").json()
            self.assertEqual(mouse["defaultView"]["selectedGeneId"], "ENSMUSG00000185591")
            self.assertEqual(mouse["assembly"], "GRCm39")
            self.assertFalse(mouse["capabilities"]["ppiPredictions"])
            self.assertEqual(mouse["featureSources"][1]["status"], "unavailable")
            self.assertEqual(mouse["featureSources"][1]["recordCount"], 0)
            for identifier, residue in (("human-gencode-v45", "M"), ("human-gencode-v50", "A"), ("human-gencode-v45", "M")):
                response = client_a.get("/api/v1/transcripts/ENST00000327443/sequence", params={"dataset": identifier})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["sequence"][0], residue)
                self.assertEqual(response.headers["x-transcript-browser-dataset"], identifier)
            self.assertEqual(client_b.get("/api/v1/transcripts/ENSMUST00000327443.9?dataset=mouse-gencode-m39").status_code, 200)
            self.assertEqual(client_a.get("/api/v1/transcripts/ENSMUST00000327443?dataset=human-gencode-v45").status_code, 404)
            self.assertEqual(client_b.get("/api/v1/search", params={"dataset": "mouse-gencode-m39", "q": "ENSMUSP00000329357.4"}).json()["results"][0]["kind"], "protein")
            self.assertEqual(client_b.get("/api/v1/region", params={"dataset": "mouse-gencode-m39", "chr": "12", "start0": 53_300_000, "end0": 53_400_000, "selected": "ENSMUST00000327443"}).status_code, 200)
            v45 = client_a.get("/api/v1/manifest?dataset=human-gencode-v45")
            v50 = client_b.get("/api/v1/manifest?dataset=human-gencode-v50", headers={"If-None-Match": v45.headers["etag"]})
            self.assertEqual(v50.status_code, 200)
            self.assertNotEqual(v45.headers["etag"], v50.headers["etag"])
            export = client_b.get("/api/v1/export", params={"dataset": "mouse-gencode-m39", "entity": "gene", "id": "ENSMUSG00000185591"})
            self.assertEqual(export.json()["_provenance"]["ensemblRelease"], 116)
            self.assertIn("mouse-gencode-m39", export.headers["content-disposition"])
            tsv = client_b.get("/api/v1/export", params={"dataset": "mouse-gencode-m39", "entity": "gene", "id": "ENSMUSG00000185591", "format": "tsv"})
            self.assertIn("_datasetId", tsv.text)
            self.assertIn("mouse-gencode-m39", tsv.text)
            empty = client_b.get("/api/v1/export", params={"dataset": "mouse-gencode-m39", "entity": "region", "chr": "12", "start0": 0, "end0": 100, "format": "tsv"})
            self.assertEqual(empty.status_code, 200)
            self.assertTrue(empty.text.startswith("# transcript-browser-provenance\t"))
            self.assertIn('"datasetId":"mouse-gencode-m39"', empty.text)
            self.assertEqual(client_a.get("/api/v1/health").json()["datasetId"], "human-gencode-v45")

    def test_missing_invalid_unknown_and_duplicate_dataset_requests_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            synthetic_dataset(root, "human-gencode-v45")
            invalid = synthetic_dataset(root, "mouse-gencode-m39")
            manifest_path = invalid / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["ensembl_release"] = 111
            manifest_path.write_text(json.dumps(manifest))
            app = create_app(project_root=root)
            client = TestClient(app, base_url="http://127.0.0.1")
            self.assertEqual(len(client.get("/api/v1/datasets").json()["datasets"]), 1)
            for path in ("/api/v1/manifest", "/api/v1/health", "/api/v1/search?q=SP1", "/api/v1/export", "/reference/genome.fa"):
                delimiter = "&" if "?" in path else "?"
                self.assertEqual(client.get(path + delimiter + "dataset=mouse-gencode-m39").status_code, 404)
                self.assertEqual(client.get(path + delimiter + "dataset=unknown").status_code, 400)
            self.assertEqual(client.get("/api/v1/manifest?dataset=human-gencode-v45&dataset=mouse-gencode-m39").status_code, 400)
            with self.assertRaises(StartupValidationError):
                create_app(project_root=root, dataset="mouse-gencode-m39")
            with self.assertRaises(StartupValidationError):
                create_app(project_root=root, dataset="human-gencode-v50")
            with self.assertRaises(StartupValidationError):
                create_app(project_root=root, dataset="unknown")

    def test_explicit_single_package_and_partial_receipt_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = synthetic_dataset(root, "mouse-gencode-m39")
            app = create_app(project_root=root, package_root=package, dataset="mouse-gencode-m39")
            self.assertEqual(app.state.default_dataset_id, "mouse-gencode-m39")
            with self.assertRaises(StartupValidationError):
                create_app(project_root=root, package_root=package, dataset="human-gencode-v45")
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["counts"]["transcript"] -= 1
            manifest_path.write_text(json.dumps(manifest))
            report_path = package / "validation_report.json"
            report = json.loads(report_path.read_text())
            report["counts"] = manifest["counts"]
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(StartupValidationError, "inventory is incomplete"):
                load_runtime_package(package, dev_fixture=False)

    def test_wrong_assembly_contig_and_reference_metadata_cannot_be_masked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = synthetic_dataset(root, "mouse-gencode-m39")
            connection = sqlite3.connect(package / "annotation.sqlite")
            connection.execute("UPDATE contig SET length=133275309 WHERE name='chr12'")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(StartupValidationError, "contig chr12 length differs"):
                load_runtime_package(package, dev_fixture=False)
            reference = package / "reference"
            reference.mkdir()
            (reference / "reference_manifest.json").write_text(json.dumps({"verified": True, "assembly": "GRCh38.p14"}))
            outer = {"assembly": "GRCm39", "reference": {"available": True, "verified": True, "assembly": "GRCm39"}}
            with self.assertRaisesRegex(StartupValidationError, "reference manifest assembly"):
                _load_reference(package, outer, full_verify=False)


if __name__ == "__main__":
    unittest.main()
