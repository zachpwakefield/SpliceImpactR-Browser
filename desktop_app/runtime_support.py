"""Shared, stdlib-only integrity helpers for locally generated Mac runtimes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "transcript-browser-macos-runtime/v1"
PACKAGE = "data/builds/gencode_v45"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def runtime_version(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "runtimeVersion"}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def safe_child(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks, including at an intermediate component."""
    parts = relative.split("/")
    if not relative or Path(relative).is_absolute() or any(part in ("", ".", "..") for part in parts) or "\x00" in relative:
        raise ValueError(f"Unsafe runtime-relative path: {relative!r}")
    child = root
    for part in parts:
        child = child / part
        if child.is_symlink():
            raise ValueError(f"Runtime path must not be a symlink: {relative}")
    return child


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != SCHEMA or manifest.get("runtimeVersion") != runtime_version(manifest):
        raise ValueError("Runtime manifest schema or content identity is invalid; rebuild the app.")
    if not isinstance(manifest.get("buildHash"), str) or not manifest["buildHash"]:
        raise ValueError("Runtime manifest has no annotation build identity.")
    executable = manifest.get("pythonExecutable")
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise ValueError("Runtime manifest has no absolute local Python interpreter.")
    for key in ("bundledFiles", "externalFiles"):
        records = manifest.get(key)
        if not isinstance(records, dict) or not records:
            raise ValueError(f"Runtime manifest lacks {key}.")
        for relative, record in records.items():
            safe_child(Path("/nonexistent-runtime-validation-root"), relative)
            if not isinstance(record, dict) or not SHA256.fullmatch(str(record.get("sha256", ""))):
                raise ValueError(f"Invalid runtime checksum for {relative}.")
            size = record.get("size")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError(f"Invalid runtime size for {relative}.")
            if key == "externalFiles" and not Path(str(record.get("source", ""))).is_absolute():
                raise ValueError(f"Invalid local source for {relative}.")
    required = {"backend/app/cli.py", "site-packages/uvicorn/__init__.py", "frontend/dist/index.html", f"{PACKAGE}/manifest.json"}
    if not required.issubset(manifest["bundledFiles"]):
        raise ValueError("Runtime manifest is missing required browser files.")
    if f"{PACKAGE}/annotation.sqlite" not in manifest["externalFiles"]:
        raise ValueError("Runtime manifest has no database clone declaration.")
    if manifest.get("frontendIndexSha256") != manifest["bundledFiles"]["frontend/dist/index.html"]["sha256"]:
        raise ValueError("Runtime frontend identity is inconsistent.")
    reference = manifest.get("reference")
    if reference is not None:
        if not isinstance(reference, dict) or not isinstance(reference.get("keys"), dict):
            raise ValueError("Runtime reference declaration is invalid.")
        for field in ("directory", "manifestName"):
            if not isinstance(reference.get(field), str):
                raise ValueError("Runtime reference paths must be strings.")
            safe_child(Path("/nonexistent-runtime-validation-root"), reference[field])
        if not {"fasta", "index", "chrom_sizes"}.issubset(reference["keys"]) or set(reference["keys"]) - {"fasta", "index", "chrom_sizes", "gzi", "aliases"}:
            raise ValueError("Runtime reference has missing or unsupported artifact keys.")
        for name in reference["keys"].values():
            if not isinstance(name, str):
                raise ValueError("Runtime reference artifact name must be a string.")
            safe_child(Path("/nonexistent-runtime-validation-root"), name)
            relative = f"external-files/reference/{name}"
            if relative not in manifest["externalFiles"]:
                raise ValueError("Runtime reference artifact is not declared as a private clone.")
        if len(set(reference["keys"].values())) != len(reference["keys"]):
            raise ValueError("Runtime reference artifact names must be unique.")


def read_manifest(root: Path) -> dict[str, Any]:
    path = safe_child(root, "runtime-manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Runtime manifest must be an object.")
    validate_manifest(manifest)
    return manifest


def verify_files(root: Path, records: dict[str, Any]) -> None:
    for relative, record in records.items():
        path = safe_child(root, relative)
        if not path.is_file() or path.stat().st_size != record["size"] or file_sha256(path) != record["sha256"]:
            raise ValueError(f"Runtime file is missing or changed: {relative}; reinstall the app.")
