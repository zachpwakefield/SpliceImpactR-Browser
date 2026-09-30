"""Optional immutable human gene-level interaction context, never predictions.

This extension is separate from the annotation build. Public SpliceImpactR
endpoint token sets are aggregated annotations: they do not preserve original
token pairings and cannot establish isoform-specific interaction gain or loss.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from backend.datasets import DatasetProfile, profile_for_metadata

from .database import AnnotationDatabase
from .errors import QueryContractError, StartupValidationError


EXPORT_SCHEMA = "transcript-browser-ppi-context-export/v1"
CONTEXT_SCHEMA = "transcript-browser-ppi-context/v1"
IMPORTER_VERSION = "transcript-browser-ppi-importer/v1"
CONTEXT_KIND = "gene-level-interaction-context"
SOURCE_NAME = "bundled SpliceImpactR BioGRID-backed DDI/DMI context"
PUBLIC_PPI_RDS_SHA256 = "49c26d895231f5b90d086accd07d489c022f9c9f5f0942860deabf19d30fae64"
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
EVIDENCE_VALUES = ("all", "feature-linked")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HUMAN_GENE_RE = re.compile(r"^ENSG[0-9]{11}$")
MAX_INPUT_LINE_BYTES = 512 * 1024
MAX_SOURCE_RECORDS = 2_000_000
MAX_SOURCE_GENES = 100_000

REQUIRED_COLUMNS = {
    "metadata": {"key", "value"},
    "interaction_record": {
        "record_id", "gene_a", "gene_b", "biogrid", "ddi", "dmi",
        "ddi_a", "ddi_b", "dmi_a", "dmi_b",
    },
    "gene_record": {"gene_id", "record_id", "partner_gene_id", "focal_endpoint", "feature_linked"},
    "gene_summary": {"gene_id", "evidence", "records", "partner_genes", "biogrid_records", "ddi_records", "dmi_records"},
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_INPUT_LINE_BYTES:
            raise StartupValidationError("PPI context manifest exceeds its bounded size.")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StartupValidationError("PPI context manifest is missing or malformed.") from exc
    if not isinstance(value, dict):
        raise StartupValidationError("PPI context manifest must contain one object.")
    return value


def regular_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
        raise StartupValidationError("PPI context artifacts must have fixed package-relative filenames.")
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise StartupValidationError("PPI context artifact must be a regular internal file.")
    return path


def validate_bound_metadata(
    metadata: Mapping[str, Any], profile: DatasetProfile, annotation_build_hash: str, *, export: bool,
    database_hash_required: bool = True,
) -> None:
    if metadata.get("schema") != (EXPORT_SCHEMA if export else CONTEXT_SCHEMA):
        raise StartupValidationError("Unsupported PPI context schema.")
    try:
        declared = profile_for_metadata(metadata)
    except ValueError as exc:
        raise StartupValidationError("PPI context annotation release/species metadata is invalid.") from exc
    if profile["species"] != "human" or declared["species"] != "human":
        raise StartupValidationError("SpliceImpactR PPI context is human-only.")
    if declared.dataset_id != profile.dataset_id or metadata.get("dataset_id") != profile.dataset_id:
        raise StartupValidationError("PPI context belongs to another annotation dataset.")
    hashes = [metadata[key] for key in ("annotation_build_hash", "annotationBuildHash") if key in metadata]
    if metadata.get("annotation_build_hash") != annotation_build_hash or not hashes or any(value != annotation_build_hash for value in hashes):
        raise StartupValidationError("PPI context belongs to another annotation build.")
    if metadata.get("kind") != CONTEXT_KIND or metadata.get("source") != SOURCE_NAME:
        raise StartupValidationError("PPI context must declare static gene-level source semantics.")
    if metadata.get("package") != "SpliceImpactR" or not re.fullmatch(r"\d+\.\d+\.\d+(?:[.-][A-Za-z0-9]+)*", str(metadata.get("package_version", ""))):
        raise StartupValidationError("PPI context public package/version provenance is invalid.")
    if metadata.get("source_rds_sha256") != PUBLIC_PPI_RDS_SHA256:
        raise StartupValidationError("PPI context is not from the verified public SpliceImpactR network input.")
    if metadata.get("network_annotation_release_matched") is not False:
        raise StartupValidationError("PPI network must not claim a verified annotation-release match.")
    if metadata.get("input_file") != "interactions.ndjson" or not SHA256_RE.fullmatch(str(metadata.get("input_sha256", ""))):
        raise StartupValidationError("PPI context stream provenance is incomplete.")
    if type(metadata.get("records")) is not int or not 1 <= metadata["records"] <= MAX_SOURCE_RECORDS:
        raise StartupValidationError("PPI context source record count is invalid.")
    if type(metadata.get("unique_genes")) is not int or not 1 <= metadata["unique_genes"] <= min(MAX_SOURCE_GENES, 2 * metadata["records"]):
        raise StartupValidationError("PPI context source gene count is invalid.")
    if not export:
        if metadata.get("importer_version") != IMPORTER_VERSION or metadata.get("database_file") != "context.sqlite":
            raise StartupValidationError("PPI context importer/database contract is invalid.")
        for key in ("context_hash", "database_sha256") if database_hash_required else ("context_hash",):
            if not SHA256_RE.fullmatch(str(metadata.get(key, ""))):
                raise StartupValidationError("PPI context integrity hashes are incomplete.")
        counts = metadata.get("counts")
        if not isinstance(counts, dict) or counts.get("records") != metadata["records"] or counts.get("unique_genes") != metadata["unique_genes"]:
            raise StartupValidationError("PPI context count metadata is incomplete.")
        for key in ("biogrid_records", "ddi_records", "dmi_records", "self_records"):
            if type(counts.get(key)) is not int or not 0 <= counts[key] <= metadata["records"]:
                raise StartupValidationError("PPI context count metadata is invalid.")


def context_identity_hash(metadata: Mapping[str, Any]) -> str:
    keys = ("schema", "importer_version", "kind", "source", "package", "package_version",
            "source_rds_sha256", "input_file", "input_sha256", "records", "unique_genes",
            "dataset_id", "species", "gencode_release", "ensembl_release", "assembly",
            "annotation_build_hash", "network_annotation_release_matched")
    return hashlib.sha256(canonical_json({key: metadata.get(key) for key in keys})).hexdigest()


def validate_input_record(raw: Any) -> dict[str, Any]:
    keys = {"geneA", "geneB", "biogrid", "ddi", "dmi", "ddiA", "ddiB", "dmiA", "dmiB"}
    if not isinstance(raw, dict) or set(raw) != keys:
        raise StartupValidationError("PPI input row has an incompatible field contract.")
    for key in ("geneA", "geneB"):
        if not isinstance(raw[key], str) or not HUMAN_GENE_RE.fullmatch(raw[key]):
            raise StartupValidationError("PPI input must use versionless human Ensembl gene IDs.")
    for key in ("biogrid", "ddi", "dmi"):
        if type(raw[key]) is not bool:
            raise StartupValidationError("PPI input flags must be nonmissing booleans.")
    for key in ("ddiA", "ddiB", "dmiA", "dmiB"):
        tokens = raw[key]
        if not isinstance(tokens, list) or any(not isinstance(token, str) or not token or len(token) > 240 for token in tokens):
            raise StartupValidationError("PPI endpoint annotations must be arrays of nonempty tokens.")
        if len(tokens) > 10_000:
            raise StartupValidationError("PPI endpoint token array exceeds the import bound.")
    for flag in ("ddi", "dmi"):
        has_a, has_b = bool(raw[flag + "A"]), bool(raw[flag + "B"])
        if (raw[flag] and not (has_a and has_b)) or (not raw[flag] and (has_a or has_b)):
            raise StartupValidationError("PPI flags contradict the recorded endpoint annotation sets.")
    return raw


@dataclass(frozen=True)
class PpiContext:
    status: str
    reason: str | None = None
    root: Path | None = None
    manifest: Mapping[str, Any] | None = None
    database: AnnotationDatabase | None = None

    @property
    def available(self) -> bool:
        return self.status == "loaded" and self.database is not None and self.manifest is not None

    def provenance(self) -> dict[str, Any] | None:
        if not self.available:
            return None
        metadata = self.manifest or {}
        return {
            "kind": CONTEXT_KIND,
            "source": SOURCE_NAME,
            "package": "SpliceImpactR",
            "packageVersion": metadata["package_version"],
            "dataSha256": metadata["source_rds_sha256"],
            "inputSha256": metadata["input_sha256"],
            "contextHash": metadata["context_hash"],
            "datasetId": metadata["dataset_id"],
            "annotationBuildHash": metadata["annotation_build_hash"],
            "species": "human",
            "resourceRelease": None,
            "resourceDate": None,
            "networkAnnotationReleaseMatched": False,
            "endpointTokenSetsAggregated": True,
            "originalTokenPairingsAvailable": False,
            "notes": "Static gene-level context, not isoform-specific predictions or a claim that every BioGRID record is a direct physical interaction. Source endpoint token sets are aggregated, not paired mechanisms; the resource release/date is not independently verified.",
        }

    def api_status(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "available": self.available,
            "predictionAvailable": False,
            "reason": self.reason,
            "sourceRecords": (self.manifest or {}).get("records") if self.available else None,
            "sourceGenes": (self.manifest or {}).get("unique_genes") if self.available else None,
            "provenance": self.provenance(),
        }

    def gene_context(
        self, gene_id: str, annotation_database: AnnotationDatabase, *, dataset_id: str,
        annotation_build_hash: str, offset: int = 0, limit: int = DEFAULT_PAGE_LIMIT,
        evidence: str = "feature-linked",
    ) -> dict[str, Any]:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE_LIMIT:
            raise QueryContractError("PPI pagination requires offset >= 0 and limit between 1 and 100.")
        if evidence not in EVIDENCE_VALUES:
            raise QueryContractError("PPI evidence must be all or feature-linked.")
        payload: dict[str, Any] = {
            "datasetId": dataset_id, "buildHash": annotation_build_hash, "geneId": gene_id,
            "status": self.status, "reason": self.reason, "predictionAvailable": False,
            "counts": None, "records": [], "provenance": self.provenance(),
            "page": {"evidence": evidence, "offset": offset, "limit": limit, "returned": 0,
                     "hasMore": False, "nextOffset": None},
        }
        if not self.available:
            return payload
        assert self.database is not None
        if (self.manifest or {}).get("dataset_id") != dataset_id or (self.manifest or {}).get("annotation_build_hash") != annotation_build_hash:
            raise QueryContractError("PPI context is not bound to the selected annotation dataset/build.")
        summary = self.database.fetch_one("SELECT * FROM gene_summary WHERE gene_id=? AND evidence=?", (gene_id, evidence)) or {}
        all_summary = self.database.fetch_one("SELECT records FROM gene_summary WHERE gene_id=? AND evidence='all'", (gene_id,)) or {}
        total = int(summary.get("records", 0))
        payload["counts"] = {
            "records": total, "allRecords": int(all_summary.get("records", 0)),
            "partnerGenes": int(summary.get("partner_genes", 0)),
            "biogridRecords": int(summary.get("biogrid_records", 0)),
            "ddiRecords": int(summary.get("ddi_records", 0)), "dmiRecords": int(summary.get("dmi_records", 0)),
        }
        linked = " AND g.feature_linked=1" if evidence == "feature-linked" else ""
        rows = self.database.fetch_all(
            "SELECT r.*,g.partner_gene_id,g.focal_endpoint FROM gene_record AS g "
            "JOIN interaction_record AS r USING(record_id) WHERE g.gene_id=?" + linked +
            " ORDER BY g.record_id LIMIT ? OFFSET ?", (gene_id, limit, offset),
        )
        partner_ids = sorted({str(row["partner_gene_id"]) for row in rows})
        known_partners: dict[str, str] = {}
        if partner_ids:
            placeholders = ",".join("?" for _ in partner_ids)
            known_partners = {str(row["gene_id"]): str(row["symbol"] or row["gene_id"])
                              for row in annotation_database.fetch_all(
                                  f"SELECT gene_id,symbol FROM gene WHERE gene_id IN ({placeholders})", partner_ids)}
        records = []
        for row in rows:
            endpoint = str(row["focal_endpoint"])
            sides = {key: json.loads(str(row[key])) for key in ("ddi_a", "ddi_b", "dmi_a", "dmi_b")}
            if endpoint == "A+B":
                focal_ddi = partner_ddi = sorted(set(sides["ddi_a"] + sides["ddi_b"]))
                focal_dmi = partner_dmi = sorted(set(sides["dmi_a"] + sides["dmi_b"]))
            else:
                focal, partner = ("a", "b") if endpoint == "A" else ("b", "a")
                focal_ddi, partner_ddi = sides["ddi_" + focal], sides["ddi_" + partner]
                focal_dmi, partner_dmi = sides["dmi_" + focal], sides["dmi_" + partner]
            partner_id = str(row["partner_gene_id"])
            records.append({
                "recordId": f"ppi:{(self.manifest or {})['context_hash'][:12]}:{row['record_id']}",
                "geneA": row["gene_a"], "geneB": row["gene_b"],
                "partner": {"id": partner_id, "symbol": known_partners.get(partner_id, partner_id),
                            "availableInDataset": partner_id in known_partners},
                "focalEndpoint": endpoint, "selfInteraction": endpoint == "A+B", "biogrid": bool(row["biogrid"]),
                "ddi": {"flag": bool(row["ddi"]), "focalPfamAccessions": focal_ddi, "partnerPfamAccessions": partner_ddi},
                "dmi": {"flag": bool(row["dmi"]), "focalTokens": focal_dmi, "partnerTokens": partner_dmi},
                "sourceEndpoints": {"geneA": row["gene_a"], "geneB": row["gene_b"],
                                    "ddiA": sides["ddi_a"], "ddiB": sides["ddi_b"],
                                    "dmiA": sides["dmi_a"], "dmiB": sides["dmi_b"]},
            })
        returned = len(records)
        has_more = offset + returned < total
        payload["records"] = records
        payload["page"].update(returned=returned, hasMore=has_more, nextOffset=offset + returned if has_more else None)
        return payload


def load_optional_ppi_context(
    project_root: Path, profile: DatasetProfile, annotation_build_hash: str, *, full_integrity: bool = False,
) -> PpiContext:
    if profile["species"] != "human":
        return PpiContext("not_applicable", "SpliceImpactR gene-level PPI context currently supports human only.")
    root = project_root / "data" / "ppi_context" / profile.dataset_id
    if not root.exists() and not root.is_symlink():
        return PpiContext("unavailable", "No optional interaction context is installed for this annotation dataset/build.")
    try:
        for directory in (root, root.parent, root.parent.parent):
            if directory.is_symlink() or not directory.is_dir():
                raise StartupValidationError("PPI context directory must remain inside the project without symbolic links.")
        metadata = read_json(regular_file(root, "manifest.json"))
        validate_bound_metadata(metadata, profile, annotation_build_hash, export=False)
        if metadata["context_hash"] != context_identity_hash(metadata):
            raise StartupValidationError("PPI context identity hash does not match its provenance.")
        path = regular_file(root, "context.sqlite")
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise StartupValidationError("PPI context has mutable SQLite journal artifacts.")
        if file_sha256(path) != metadata["database_sha256"]:
            raise StartupValidationError("PPI context database checksum does not match its manifest.")
        database = AnnotationDatabase(path)
        for table, required in REQUIRED_COLUMNS.items():
            if not database.table_exists(table) or not required.issubset(database.table_columns(table)):
                raise StartupValidationError("PPI context database schema is incompatible.")
        internal = {str(row["key"]): json.loads(str(row["value"])) for row in database.fetch_all("SELECT key,value FROM metadata")}
        validate_bound_metadata(internal, profile, annotation_build_hash, export=False, database_hash_required=False)
        for key, value in internal.items():
            if key == "database_sha256":
                continue  # A database cannot contain its own final byte digest.
            if metadata.get(key) != value:
                raise StartupValidationError("PPI context manifest and database metadata disagree.")
        actual = database.fetch_one("SELECT COUNT(*) AS records FROM interaction_record")
        if actual is None or actual["records"] != metadata["records"]:
            raise StartupValidationError("PPI context record inventory is incomplete.")
        summaries = database.fetch_one("SELECT COUNT(*) AS genes,SUM(records) AS indexed_records FROM gene_summary WHERE evidence='all'") or {}
        adjacency = database.fetch_one("SELECT COUNT(*) AS records FROM gene_record") or {}
        self_records = (metadata.get("counts") or {}).get("self_records")
        if (type(self_records) is not int or not 0 <= self_records <= metadata["records"]
            or summaries.get("genes") != metadata["unique_genes"]
            or adjacency.get("records") != 2 * metadata["records"] - self_records
            or summaries.get("indexed_records") != adjacency.get("records")):
            raise StartupValidationError("PPI context partner/summary inventory is incomplete.")
        with database.connect() as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='gene_record_feature'").fetchone():
                raise StartupValidationError("PPI context pagination index is missing.")
            if full_integrity and connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StartupValidationError("PPI context SQLite integrity check failed.")
        return PpiContext("loaded", root=root, manifest=metadata, database=database)
    except (StartupValidationError, OSError, ValueError, sqlite3.Error) as exc:
        reason = str(exc) if isinstance(exc, StartupValidationError) else "PPI context failed integrity validation."
        return PpiContext("unavailable", reason)


def absent_ppi_context(profile: DatasetProfile) -> PpiContext:
    return PpiContext("not_applicable", "SpliceImpactR gene-level PPI context currently supports human only.") if profile["species"] != "human" else PpiContext("unavailable", "No optional interaction context is installed for this annotation dataset/build.")
