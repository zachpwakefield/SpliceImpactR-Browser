"""Validate a fresh SpliceImpactR preparation without workstation-specific pins."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .constants import (
    ANNOTATION_POLICY, ASSEMBLY, ENSEMBL_RELEASE, EXPECTED_GTF_FEATURE_ROWS,
    FEATURE_COLUMNS, FEATURE_QUERY_POLICY, FEATURE_SOURCES, PREPARATION_MANIFEST, PREPARATION_SCHEMA,
    REQUIRED_INPUTS,
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


def read_preparation_manifest(source: Path) -> dict[str, Any]:
    path = source / PREPARATION_MANIFEST
    if not path.is_file():
        raise ValueError(
            "Missing spliceimpactr_manifest.json. Run scripts/prepare_spliceimpactr_cache.R "
            "to prepare the complete, unfiltered annotation and feature receipts."
        )
    if path.stat().st_size > 1_000_000:
        raise ValueError("Preparation manifest is unexpectedly large")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != PREPARATION_SCHEMA:
        raise ValueError("Old or unsupported preparation manifest; rerun scripts/prepare_spliceimpactr_cache.R")
    if (manifest.get("gencode_release"), manifest.get("ensembl_release"), manifest.get("assembly")) != (45, ENSEMBL_RELEASE, ASSEMBLY):
        raise ValueError("Preparation must pair GENCODE v45 with Ensembl 111 / GRCh38.p14")
    if manifest.get("annotation_policy") != ANNOTATION_POLICY:
        raise ValueError("Browser preparation must retain all TSLs, biotypes, and incomplete CDS models")
    query_policy = manifest.get("feature_query_policy")
    if not isinstance(query_policy, dict) or any(key not in query_policy or query_policy[key] != value for key, value in FEATURE_QUERY_POLICY.items()):
        raise ValueError("Preparation must use the pinned archive without biotype filtering or test fixtures")
    inventory = manifest.get("annotation_inventory")
    if not isinstance(inventory, dict):
        raise ValueError("Preparation lacks the complete annotation inventory")
    for kind, expected in (("genes", EXPECTED_GTF_FEATURE_ROWS["gene"]), ("transcripts", EXPECTED_GTF_FEATURE_ROWS["transcript"])):
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
    if not isinstance(raw, dict) or set(raw) != set(REQUIRED_INPUTS):
        raise ValueError("Preparation must record all three raw GENCODE files")
    for filename, expected_md5 in REQUIRED_INPUTS.items():
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
        for field in ("distinct_transcripts", "distinct_feature_ids"):
            if _count(record.get(field), f"{name} {field}") > rows:
                raise ValueError(f"Preparation {name} {field} exceeds its row count")
    return manifest
