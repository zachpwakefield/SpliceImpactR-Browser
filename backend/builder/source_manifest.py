"""Validate a fresh SpliceImpactR preparation without workstation-specific pins."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from backend.datasets import DatasetProfile, profile_for_metadata

from .constants import (
    ANNOTATION_POLICY,
    FEATURE_COLUMNS, FEATURE_QUERY_POLICY, FEATURE_SOURCES, PREPARATION_MANIFEST, PREPARATION_SCHEMA,
)


def transcript_inventory_digest(identifiers: Iterable[str]) -> str:
    return hashlib.sha256("".join(f"{value}\n" for value in sorted(set(identifiers))).encode("utf-8")).hexdigest()


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Preparation {label} must be a non-negative integer")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"Preparation {label} must be a SHA-256 digest")
    return value


def read_preparation_manifest(source: Path, profile: DatasetProfile | None = None) -> dict[str, Any]:
    path = source / PREPARATION_MANIFEST
    if not path.is_file():
        raise ValueError(
            "Missing spliceimpactr_manifest.json. Run scripts/prepare_spliceimpactr_cache.R "
            "to prepare the complete, unfiltered annotation and feature receipts."
        )
    if path.stat().st_size > 1_000_000:
        raise ValueError("Preparation manifest is unexpectedly large")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") not in {PREPARATION_SCHEMA, "transcript-browser-spliceimpactr-cache/v3"}:
        raise ValueError("Old or unsupported preparation manifest; rerun scripts/prepare_spliceimpactr_cache.R")
    resolved = profile_for_metadata(manifest, legacy_v45=manifest["schema"] == PREPARATION_SCHEMA)
    if profile is not None and resolved.dataset_id != profile.dataset_id:
        raise ValueError(f"Preparation dataset {resolved.dataset_id} does not match requested {profile.dataset_id}")
    profile = resolved
    if manifest.get("annotation_policy") != ANNOTATION_POLICY:
        raise ValueError("Browser preparation must retain all TSLs, biotypes, and incomplete CDS models")
    query_policy = manifest.get("feature_query_policy")
    expected_query = {**FEATURE_QUERY_POLICY, "provider": profile.feature_provider}
    if not isinstance(query_policy, dict) or any(key not in query_policy or query_policy[key] != value for key, value in expected_query.items()):
        raise ValueError("Preparation must use the pinned archive without biotype filtering or test fixtures")
    if manifest["schema"].endswith("/v3"):
        biomart = manifest.get("biomart") or {}
        for key in ("host", "dataset", "registry_database"):
            if biomart.get(key) != profile["biomart"][key]:
                raise ValueError(f"Preparation BioMart {key} differs from the verified dataset profile")
    inventory = manifest.get("annotation_inventory")
    if not isinstance(inventory, dict):
        raise ValueError("Preparation lacks the complete annotation inventory")
    for kind, expected in (("genes", profile["expected"]["gtf_feature_rows"]["gene"]), ("transcripts", profile["expected"]["gtf_feature_rows"]["transcript"])):
        if _count(inventory.get(kind), kind) != expected:
            raise ValueError(f"Preparation {kind} inventory is incomplete: expected {expected:,}")
    _sha256(inventory.get("transcript_ids_sha256"), "transcript inventory")
    producer = manifest.get("producer")
    if not isinstance(producer, dict) or producer.get("package") != "SpliceImpactR":
        raise ValueError("Preparation must record its SpliceImpactR producer")
    version = producer.get("version", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version) or int(version.split(".")[0]) < 1:
        raise ValueError("Preparation requires the released SpliceImpactR package (>= 1.0.0)")
    if manifest.get("required_feature_columns") != list(FEATURE_COLUMNS):
        raise ValueError("Preparation feature-column contract differs from the browser")
    raw = manifest.get("raw_inputs")
    if not isinstance(raw, dict) or set(raw) != set(profile.required_inputs):
        raise ValueError("Preparation must record all three raw GENCODE files")
    for filename, expected_md5 in profile.required_inputs.items():
        record = raw[filename]
        if not isinstance(record, dict) or record.get("file") != filename or record.get("md5") != expected_md5:
            raise ValueError(f"Preparation raw-file identity mismatch: {filename}")
        if not _count(record.get("size"), f"{filename} size"):
            raise ValueError(f"Preparation raw file is empty: {filename}")
    sources = manifest.get("feature_sources")
    if not isinstance(sources, dict) or set(sources) != set(FEATURE_SOURCES):
        raise ValueError("Preparation must record all seven feature sources")
    for name, filename in FEATURE_SOURCES.items():
        record = sources[name]
        if not isinstance(record, dict) or record.get("file") != filename:
            raise ValueError(f"Preparation feature filename mismatch: {name}")
        _sha256(record.get("sha256"), filename)
        if not _count(record.get("size"), f"{filename} size"):
            raise ValueError(f"Preparation feature file is empty: {filename}")
        rows = _count(record.get("rows"), f"{name} rows")
        if manifest["schema"].endswith("/v3"):
            retrieval = record.get("retrieval") or {}
            if not isinstance(retrieval, dict):
                raise ValueError(f"Preparation {name} retrieval evidence must be an object")
            status = record.get("status", retrieval.get("status"))
            if "status" in record and "status" in retrieval and record["status"] != retrieval["status"]:
                raise ValueError(f"Preparation {name} contains conflicting source availability statuses")
            expected_retrieval = {"species": profile["species"], "host": profile["biomart"]["host"], "dataset": profile["biomart"]["dataset"], "registry_database": profile["biomart"]["registry_database"]}
            for key, value in expected_retrieval.items():
                if key in retrieval and retrieval[key] != value:
                    raise ValueError(f"Preparation {name} retrieval {key} differs from the verified dataset profile")
            for key in ("release", "ensembl_release", "ensemblRelease"):
                if key in retrieval and str(retrieval[key]) != str(profile["ensembl_release"]):
                    raise ValueError(f"Preparation {name} retrieval release differs from the verified Ensembl release")
            if status not in {"available", "available-empty", "unavailable"}:
                raise ValueError(f"Preparation {name} lacks an explicit retrieval availability status")
            if status != "available" and rows != 0:
                raise ValueError(f"Preparation {name} unavailable/empty source cannot contain feature rows")
            if status == "unavailable" and not record.get("reason", retrieval.get("reason")):
                raise ValueError(f"Preparation {name} unavailable source requires a reason")
        for field in ("distinct_transcripts", "distinct_feature_ids"):
            if _count(record.get(field), f"{name} {field}") > rows:
                raise ValueError(f"Preparation {name} {field} exceeds its row count")
    return manifest
