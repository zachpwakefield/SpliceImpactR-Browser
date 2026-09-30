"""Stream a public SpliceImpactR PPI export into a separate immutable sidecar.

Usage: python -m backend.builder.ppi_context --source EXPORT_DIR --dataset ID
The source is produced by scripts/export_ppi_context.R. No annotation database
or annotation manifest is modified, and an existing sidecar is never replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any

from backend.app.errors import StartupValidationError
from backend.app.package import RuntimePackage, load_runtime_package
from backend.app.ppi_context import (
    CONTEXT_SCHEMA, IMPORTER_VERSION, MAX_INPUT_LINE_BYTES, canonical_json,
    context_identity_hash, file_sha256, read_json, regular_file,
    validate_bound_metadata, validate_input_record,
)
from backend.datasets import get_dataset_profile

from .build import build_lock


SCHEMA_SQL = """
CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE interaction_record (
    record_id INTEGER PRIMARY KEY CHECK(record_id>0),
    gene_a TEXT NOT NULL,gene_b TEXT NOT NULL,
    biogrid INTEGER NOT NULL CHECK(biogrid IN(0,1)),
    ddi INTEGER NOT NULL CHECK(ddi IN(0,1)),dmi INTEGER NOT NULL CHECK(dmi IN(0,1)),
    ddi_a TEXT NOT NULL,ddi_b TEXT NOT NULL,dmi_a TEXT NOT NULL,dmi_b TEXT NOT NULL
);
CREATE TABLE gene_record (
    gene_id TEXT NOT NULL,record_id INTEGER NOT NULL REFERENCES interaction_record(record_id),
    partner_gene_id TEXT NOT NULL,focal_endpoint TEXT NOT NULL CHECK(focal_endpoint IN('A','B','A+B')),
    feature_linked INTEGER NOT NULL CHECK(feature_linked IN(0,1)),
    PRIMARY KEY(gene_id,record_id)
) WITHOUT ROWID;
CREATE TABLE gene_summary (
    gene_id TEXT NOT NULL,evidence TEXT NOT NULL CHECK(evidence IN('all','feature-linked')),
    records INTEGER NOT NULL,partner_genes INTEGER NOT NULL,
    biogrid_records INTEGER NOT NULL,ddi_records INTEGER NOT NULL,dmi_records INTEGER NOT NULL,
    PRIMARY KEY(gene_id,evidence)
) WITHOUT ROWID;
"""


def _runtime_metadata(receipt: dict[str, Any], package: RuntimePackage) -> dict[str, Any]:
    profile = package.profile
    return {
        "schema": CONTEXT_SCHEMA, "importer_version": IMPORTER_VERSION,
        "kind": receipt["kind"], "source": receipt["source"], "package": receipt["package"],
        "package_version": receipt["package_version"], "source_rds_sha256": receipt["source_rds_sha256"],
        "input_file": receipt["input_file"], "input_sha256": receipt["input_sha256"],
        "records": receipt["records"], "unique_genes": receipt["unique_genes"],
        "dataset_id": profile.dataset_id, "species": profile["species"],
        "gencode_release": profile["gencode_release"], "ensembl_release": profile["ensembl_release"],
        "assembly": profile["assembly"], "annotation_build_hash": package.build_hash,
        "network_annotation_release_matched": False, "database_file": "context.sqlite",
    }


def build_ppi_context(source: Path, package: RuntimePackage, output: Path) -> dict[str, Any]:
    if package.profile["species"] != "human":
        raise StartupValidationError("SpliceImpactR PPI context is human-only; no mouse sidecar will be built.")
    source = source.expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise StartupValidationError("PPI export source must be a regular directory.")
    receipt = read_json(regular_file(source, "context_manifest.json"))
    validate_bound_metadata(receipt, package.profile, package.build_hash, export=True)
    stream = regular_file(source, "interactions.ndjson")
    output = output.expanduser().absolute()
    try:
        output.resolve().relative_to(package.root.resolve())
    except ValueError:
        pass
    else:
        raise StartupValidationError("PPI context must remain separate from the authoritative annotation build.")
    if output.exists() or output.is_symlink():
        raise StartupValidationError("An interaction sidecar already exists; refusing to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink():
        raise StartupValidationError("PPI sidecar output parent must not be a symbolic link.")
    with build_lock(output):
        if output.exists() or output.is_symlink():
            raise StartupValidationError("An interaction sidecar was published by another builder.")
        staged = Path(tempfile.mkdtemp(prefix=".ppi-context-", dir=output.parent))
        connection: sqlite3.Connection | None = None
        try:
            database = staged / "context.sqlite"
            connection = sqlite3.connect(database)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA cache_size=-32768")
            connection.execute("PRAGMA temp_store=FILE")
            connection.executescript(SCHEMA_SQL)
            digest = hashlib.sha256()
            source_genes: set[str] = set()
            counts = {"records": 0, "biogrid_records": 0, "ddi_records": 0, "dmi_records": 0, "self_records": 0}
            with stream.open("rb") as handle:
                while raw_line := handle.readline(MAX_INPUT_LINE_BYTES + 1):
                    if len(raw_line) > MAX_INPUT_LINE_BYTES:
                        raise StartupValidationError("PPI source row exceeds the bounded NDJSON import size.")
                    digest.update(raw_line)
                    try:
                        raw = validate_input_record(json.loads(raw_line))
                    except (ValueError, UnicodeError) as exc:
                        raise StartupValidationError("PPI source row is not valid JSON.") from exc
                    counts["records"] += 1
                    ordinal = counts["records"]
                    if ordinal > receipt["records"]:
                        raise StartupValidationError("PPI stream contains more records than its receipt.")
                    a, b = raw["geneA"], raw["geneB"]
                    source_genes.update((a, b))
                    if len(source_genes) > receipt["unique_genes"]:
                        raise StartupValidationError("PPI stream contains more source genes than its receipt.")
                    for flag in ("biogrid", "ddi", "dmi"):
                        counts[flag + "_records"] += int(raw[flag])
                    counts["self_records"] += int(a == b)
                    connection.execute(
                        "INSERT INTO interaction_record VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (ordinal, a, b, int(raw["biogrid"]), int(raw["ddi"]), int(raw["dmi"]),
                         *(canonical_json(raw[key]).decode("utf-8") for key in ("ddiA", "ddiB", "dmiA", "dmiB"))),
                    )
                    linked = int(raw["ddi"] or raw["dmi"])
                    if a == b:
                        connection.execute("INSERT INTO gene_record VALUES(?,?,?,?,?)", (a, ordinal, b, "A+B", linked))
                    else:
                        connection.execute("INSERT INTO gene_record VALUES(?,?,?,?,?)", (a, ordinal, b, "A", linked))
                        connection.execute("INSERT INTO gene_record VALUES(?,?,?,?,?)", (b, ordinal, a, "B", linked))
            if digest.hexdigest() != receipt["input_sha256"]:
                raise StartupValidationError("PPI NDJSON checksum differs from its export receipt.")
            if counts["records"] != receipt["records"] or len(source_genes) != receipt["unique_genes"]:
                raise StartupValidationError("PPI source record/gene inventory differs from its export receipt.")
            connection.execute("CREATE INDEX gene_record_feature ON gene_record(gene_id,feature_linked,record_id)")
            for evidence, condition in (("all", ""), ("feature-linked", " WHERE g.feature_linked=1")):
                connection.execute(
                    "INSERT INTO gene_summary SELECT g.gene_id,?,COUNT(*),COUNT(DISTINCT g.partner_gene_id),"
                    "SUM(r.biogrid),SUM(r.ddi),SUM(r.dmi) FROM gene_record AS g "
                    "JOIN interaction_record AS r USING(record_id)" + condition + " GROUP BY g.gene_id", (evidence,),
                )
            metadata = _runtime_metadata(receipt, package)
            metadata["context_hash"] = context_identity_hash(metadata)
            metadata["counts"] = {**counts, "unique_genes": len(source_genes)}
            connection.executemany("INSERT INTO metadata VALUES(?,?)",
                                   [(key, canonical_json(value).decode("utf-8")) for key, value in sorted(metadata.items())])
            connection.commit()
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StartupValidationError("PPI sidecar failed SQLite integrity verification.")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StartupValidationError("PPI sidecar has orphaned interaction records.")
            connection.close()
            connection = None
            metadata["database_sha256"] = file_sha256(database)
            (staged / "manifest.json").write_bytes(canonical_json(metadata) + b"\n")
            # Refuse concurrent publication rather than merging or replacing
            # any existing optional context or the authoritative annotation.
            if output.exists() or output.is_symlink():
                raise StartupValidationError("An interaction sidecar appeared before publication.")
            os.rename(staged, output)
            return metadata
        finally:
            if connection is not None:
                connection.close()
            if staged.exists():
                shutil.rmtree(staged)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Directory from scripts/export_ppi_context.R.")
    parser.add_argument("--dataset", required=True, help="Exact human dataset ID to bind this context to.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--data-package", type=Path, help="Optional explicit validated annotation package.")
    parser.add_argument("--output", type=Path, help="Default: data/ppi_context/<datasetId>; an existing directory is never replaced.")
    args = parser.parse_args()
    try:
        profile = get_dataset_profile(args.dataset)
        root = args.project_root.expanduser().resolve()
        package_path = args.data_package or root / "data" / "builds" / profile["package_dir"]
        package = load_runtime_package(package_path, dev_fixture=False)
        if package.dataset_id != args.dataset:
            raise StartupValidationError("The annotation package does not match the requested PPI dataset.")
        result = build_ppi_context(args.source, package, args.output or root / "data" / "ppi_context" / args.dataset)
    except (StartupValidationError, OSError, ValueError, RuntimeError) as exc:
        print(f"PPI context build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "built", "datasetId": result["dataset_id"], "annotationBuildHash": result["annotation_build_hash"],
                      "contextHash": result["context_hash"], "sourceRecords": result["records"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
