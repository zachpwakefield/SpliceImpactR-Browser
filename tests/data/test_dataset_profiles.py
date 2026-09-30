from __future__ import annotations

import copy
import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from backend.builder.build import BuildError, import_features, ingest_fastas, ingest_gtf, insert_contigs, validate_density_tiles
from backend.builder.constants import FEATURE_COLUMNS, FEATURE_SOURCES, PREPARATION_MANIFEST
from backend.builder.parsers import ucsc_bin
from backend.builder.schema import connect_database, create_schema, populate_density_tiles
from backend.builder.source_manifest import read_preparation_manifest
from backend.datasets import dataset_profiles, get_dataset_profile
from tests.data.test_source_manifest import manifest_fixture


def modern_manifest(dataset_id: str) -> dict:
    profile = get_dataset_profile(dataset_id)
    value = manifest_fixture()
    value.update(schema="transcript-browser-spliceimpactr-cache/v3", dataset_id=dataset_id, species=profile["species"], gencode_release=profile["gencode_release"], ensembl_release=profile["ensembl_release"], assembly=profile["assembly"], biomart=dict(profile["biomart"]))
    value["feature_query_policy"]["provider"] = profile.feature_provider
    value["annotation_inventory"].update(genes=profile["expected"]["gtf_feature_rows"]["gene"], transcripts=profile["expected"]["gtf_feature_rows"]["transcript"])
    value["raw_inputs"] = {name: {"file": name, "md5": md5, "size": 10} for name, md5 in profile.required_inputs.items()}
    for receipt in value["feature_sources"].values():
        receipt["status"] = "available"
    return value


class DatasetPreparationTests(unittest.TestCase):
    def test_every_profile_contig_matches_independently_verified_assembly_metadata(self) -> None:
        from backend.builder.constants import PRIMARY_CONTIG_LENGTHS
        fixtures = Path(__file__).parent / "fixtures"
        for dataset_id in dataset_profiles():
            profile = get_dataset_profile(dataset_id)
            assembly = "hg38" if profile["species"] == "human" else "mm39"
            official = {}
            for line in (fixtures / (assembly + ".primary.chrom.sizes")).read_text().splitlines():
                if not line.startswith("#"):
                    name, length = line.split("\t")
                    official[name] = int(length)
            self.assertEqual(dict(profile.contigs), official)
            if profile["species"] == "human":
                self.assertEqual(dict(profile.contigs), dict(PRIMARY_CONTIG_LENGTHS))
                self.assertEqual(profile.contigs["chr18"], 80_373_285)

    def test_all_profiles_have_verified_nonnull_full_inventory(self) -> None:
        for dataset_id in dataset_profiles():
            profile = get_dataset_profile(dataset_id)
            counts = profile["expected"]
            self.assertEqual(sum(counts["gtf_feature_rows"].values()), counts["gtf_total_rows"])
            for key in ("pc_transcript_fasta_records", "pc_translation_fasta_records"):
                self.assertIsInstance(counts[key], int)
                self.assertGreater(counts[key], 0)

    def test_v3_profile_registry_species_and_raw_identity_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for dataset_id in (identifier for identifier in dataset_profiles() if identifier != "human-gencode-v45"):
                manifest = modern_manifest(dataset_id)
                path = root / PREPARATION_MANIFEST
                path.write_text(json.dumps(manifest))
                self.assertEqual(read_preparation_manifest(root, get_dataset_profile(dataset_id)), manifest)
                for field, bad in (("species", "human" if dataset_id.startswith("mouse") else "mouse"), ("ensembl_release", 50), ("assembly", "GRCm38"), ("gencode_release", 45)):
                    mutated = {**manifest, field: bad}
                    path.write_text(json.dumps(mutated))
                    with self.subTest(dataset=dataset_id, field=field), self.assertRaises(ValueError):
                        read_preparation_manifest(root)
                for field, bad in (("host", "https://www.ensembl.org"), ("dataset", "rat_gene_ensembl"), ("registry_database", "ensembl_mart_115")):
                    mutated = copy.deepcopy(manifest)
                    mutated["biomart"][field] = bad
                    path.write_text(json.dumps(mutated))
                    with self.subTest(dataset=dataset_id, registry=field), self.assertRaises(ValueError):
                        read_preparation_manifest(root)
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    read_preparation_manifest(root, get_dataset_profile("human-gencode-v45"))

    def test_unavailable_vs_valid_empty_sources_require_explicit_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = modern_manifest("mouse-gencode-m39")
            elm = manifest["feature_sources"]["elm"]
            elm.update(status="unavailable", reason="Provider attributes absent in verified mouse archive", rows=0, distinct_transcripts=0, distinct_feature_ids=0)
            path = root / PREPARATION_MANIFEST
            path.write_text(json.dumps(manifest))
            self.assertEqual(read_preparation_manifest(root), manifest)
            elm.pop("reason")
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "requires a reason"):
                read_preparation_manifest(root)
            elm["status"] = "available-empty"
            path.write_text(json.dumps(manifest))
            self.assertEqual(read_preparation_manifest(root), manifest)
            elm["rows"] = 1
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                read_preparation_manifest(root)

    def test_contradictory_per_source_retrieval_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = get_dataset_profile("mouse-gencode-m39")
            manifest = modern_manifest(profile.dataset_id)
            manifest["feature_sources"]["pfam"]["retrieval"] = {"status": "available", "species": "mouse", "host": profile["biomart"]["host"], "dataset": profile["biomart"]["dataset"], "release": 116}
            path = root / PREPARATION_MANIFEST
            path.write_text(json.dumps(manifest))
            self.assertEqual(read_preparation_manifest(root), manifest)
            for key, value in (("status", "unavailable"), ("species", "human"), ("host", "https://www.ensembl.org"), ("dataset", "hsapiens_gene_ensembl"), ("release", 111)):
                modified = copy.deepcopy(manifest)
                modified["feature_sources"]["pfam"]["retrieval"][key] = value
                path.write_text(json.dumps(modified))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    read_preparation_manifest(root)

    def test_mouse_contig_lengths_density_aliases_and_wrong_species_gtf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect_database(root / "annotation.sqlite")
            create_schema(connection)
            profile = get_dataset_profile("mouse-gencode-m39")
            insert_contigs(connection, profile)
            self.assertEqual(connection.execute("SELECT length FROM contig WHERE name='chr1'").fetchone()[0], 195_154_279)
            self.assertEqual(connection.execute("SELECT contig_name FROM contig_alias WHERE alias='MT'").fetchone()[0], "chrM")
            self.assertIsNone(connection.execute("SELECT name FROM contig WHERE name='chr22'").fetchone())
            populate_density_tiles(connection)
            self.assertEqual(validate_density_tiles(connection), [])
            gtf = root / "wrong.gtf.gz"
            with gzip.open(gtf, "wt") as handle:
                handle.write('chr1\tHAVANA\tgene\t101\t200\t.\t+\t.\tgene_id "ENSG00000000001.1"; gene_name "Sp1"; gene_type "protein_coding";\n')
            with self.assertRaisesRegex(BuildError, "does not match selected species"):
                ingest_gtf(connection, gtf, "fixture", profile)
            connection.close()

    def test_wrong_peptide_identity_never_projects_even_with_valid_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect_database(root / "annotation.sqlite")
            create_schema(connection)
            insert_contigs(connection, get_dataset_profile("mouse-gencode-m39"))
            connection.execute("INSERT INTO gene(gene_id,gene_id_versioned,symbol,biotype,contig,start0,end0,strand,bin) VALUES(?,?,?,?,?,?,?,?,?)", ("ENSMUSG00000000001", "ENSMUSG00000000001.1", "Test", "protein_coding", "chr1", 100, 130, "+", ucsc_bin(100,130)))
            connection.execute("INSERT INTO transcript(transcript_id,transcript_id_versioned,gene_id,transcript_name,biotype,protein_id,protein_id_versioned,protein_version,protein_length,contig,start0,end0,strand,bin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("ENSMUST00000000001", "ENSMUST00000000001.1", "ENSMUSG00000000001", "Test-201", "protein_coding", "ENSMUSP00000000001", "ENSMUSP00000000001.1", 1, 10, "chr1", 100, 130, "+", ucsc_bin(100,130)))
            connection.execute("INSERT INTO translation_mapping(transcript_id,status,reason) VALUES(?,?,?)", ("ENSMUST00000000001", "exact", "Synthetic exact translation fixture"))
            exports = root / "exports"
            exports.mkdir()
            for source in FEATURE_SOURCES:
                with (exports / (source + ".tsv")).open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS, delimiter="\t")
                    writer.writeheader()
                    if source == "pfam":
                        writer.writerow({"ensembl_transcript_id": "ENSMUST00000000001", "ensembl_peptide_id": "ENSMUSP00000000999", "start": 1, "stop": 2, "chr": "1", "strand": "+", "feature_id": "PF00001"})
            summary = import_features(connection, exports)
            self.assertEqual(summary["feature_counts"]["pfam"], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM protein_feature_segment").fetchone()[0], 0)
            self.assertIn("protein identifier mismatch", summary["invalid_rows"][0])
            connection.close()

    def test_fasta_release_model_version_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            connection = connect_database(root / "annotation.sqlite")
            create_schema(connection)
            profile = get_dataset_profile("mouse-gencode-m39")
            insert_contigs(connection, profile)
            connection.execute("INSERT INTO gene(gene_id,gene_id_versioned,symbol,biotype,contig,start0,end0,strand,bin) VALUES(?,?,?,?,?,?,?,?,?)", ("ENSMUSG00000000001", "ENSMUSG00000000001.1", "Test", "protein_coding", "chr1", 100, 130, "+", ucsc_bin(100,130)))
            connection.execute("INSERT INTO transcript(transcript_id,transcript_id_versioned,gene_id,transcript_name,biotype,protein_id,protein_id_versioned,protein_version,contig,start0,end0,strand,bin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", ("ENSMUST00000000001", "ENSMUST00000000001.1", "ENSMUSG00000000001", "Test-201", "protein_coding", "ENSMUSP00000000001", "ENSMUSP00000000001.1", 1, "chr1", 100, 130, "+", ucsc_bin(100,130)))
            transcript_path = root / profile.filename("transcripts")
            protein_path = root / profile.filename("translations")
            connection.commit()
            with gzip.open(transcript_path, "wt") as handle:
                handle.write(">ENSMUST00000000001.2|ENSMUSG00000000001.1|-|-|Test-201|Test|3|CDS:1-3\nATG\n")
            with gzip.open(protein_path, "wt") as handle:
                handle.write(">ENSMUSP00000000001.1|ENSMUST00000000001.1|1\nM\n")
            with self.assertRaisesRegex(BuildError, "Transcript FASTA identity differs"):
                ingest_fastas(connection, root, profile)
            with gzip.open(transcript_path, "wt") as handle:
                handle.write(">ENSMUST00000000001.1|ENSMUSG00000000001.1|-|-|Test-201|Test|3|CDS:1-3\nATG\n")
            with gzip.open(protein_path, "wt") as handle:
                handle.write(">ENSMUSP00000000999.1|ENSMUST00000000001.1|1\nM\n")
            with self.assertRaisesRegex(BuildError, "Protein FASTA peptide identity differs"):
                ingest_fastas(connection, root, profile)
            connection.close()


if __name__ == "__main__":
    unittest.main()
