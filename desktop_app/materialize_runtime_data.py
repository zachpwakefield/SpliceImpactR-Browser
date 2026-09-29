#!/usr/bin/env python3
"""Install private data clones without modifying the source annotation package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_app.runtime_support import PACKAGE, canonical_json, file_sha256, read_manifest, safe_child, verify_files


def clone_verified(source: Path, destination: Path, metadata: dict) -> None:
    if not source.is_file() or source.stat().st_size != metadata["size"]:
        raise ValueError("A declared scientific source is missing or changed; rebuild the app.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Refusing to overwrite a runtime data destination.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    cloned = False
    if sys.platform == "darwin":
        result = subprocess.run(["/bin/cp", "-c", str(source), str(destination)], capture_output=True, check=False)
        cloned = result.returncode == 0
        if not cloned and destination.exists():
            destination.unlink()
    if not cloned:
        shutil.copyfile(source, destination)
    if destination.stat().st_size != metadata["size"] or file_sha256(destination) != metadata["sha256"]:
        destination.unlink()
        raise ValueError("Scientific clone checksum mismatch; the source changed or copying failed.")
    destination.chmod(0o444)


def _materialize_reference(staging: Path, final: Path, manifest: dict) -> None:
    reference = manifest.get("reference")
    if reference is None:
        return
    directory = reference["directory"]
    reference_root = safe_child(staging, directory)
    reference_root.mkdir(parents=True, exist_ok=True)
    declarations = {}
    records = []
    for key, public_name in reference["keys"].items():
        relative = f"external-files/reference/{public_name}"
        metadata = manifest["externalFiles"][relative]
        cloned = safe_child(staging, relative)
        final_target = safe_child(final, relative)
        link = safe_child(reference_root, public_name)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists():
            raise ValueError("Reference link destination already exists.")
        link.symlink_to(final_target)
        stat = cloned.stat()
        declaration = {"public_name": public_name, "link_path": public_name, "target_path": str(final_target), "sha256": metadata["sha256"], "size": metadata["size"]}
        declarations[key] = declaration
        records.append({**declaration, "path": public_name, "inode": stat.st_ino, "mtime_ns": stat.st_mtime_ns})
    reference_manifest = {"assembly": "GRCh38.p14", "verified": True, "verification_receipt": "verification_receipt.json", **declarations}
    manifest_path = safe_child(reference_root, reference["manifestName"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_json(reference_manifest))
    safe_child(reference_root, "verification_receipt.json").write_bytes(canonical_json({"files": records}))


def verify_cached_runtime(root: Path, *, full_verify: bool = True) -> dict:
    from backend.app.main import create_app

    if root.is_symlink():
        raise ValueError("The runtime directory must not be a symlink.")
    root = root.resolve()
    manifest = read_manifest(root)
    verify_files(root, manifest["bundledFiles"])
    if full_verify:
        verify_files(root, manifest["externalFiles"])
    app = create_app(project_root=root, full_database_verify=full_verify, full_reference_verify=full_verify)
    if app.state.runtime_package.build_hash != manifest["buildHash"]:
        raise ValueError("Installed annotation and runtime build identities differ.")
    return manifest


def materialize_runtime(project_root: Path, staging: Path, final: Path) -> dict:
    if staging.is_symlink() or final.is_symlink() or final.exists():
        raise ValueError("Refusing to replace an existing runtime; verify it or install a new runtime version.")
    staging = staging.resolve()
    final = final.absolute().parent.resolve() / final.name
    if staging == final or staging.parent != final.parent:
        raise ValueError("Staging and final runtimes must be separate sibling locations.")
    manifest = read_manifest(staging)
    verify_files(staging, manifest["bundledFiles"])
    database_source = Path(manifest["externalFiles"][f"{PACKAGE}/annotation.sqlite"]["source"])
    if database_source.resolve() != (project_root.resolve() / PACKAGE / "annotation.sqlite").resolve():
        raise ValueError("The runtime database source differs from this checkout; rebuild the app here.")
    for relative, metadata in manifest["externalFiles"].items():
        clone_verified(Path(metadata["source"]), safe_child(staging, relative), metadata)
    _materialize_reference(staging, final, manifest)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging, final)
    try:
        # Symlinks target final paths, never the temporary staging directory.
        verify_cached_runtime(final, full_verify=False)
    except Exception:
        os.rename(final, staging)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--verify-cached", type=Path)
    args = parser.parse_args()
    try:
        if args.verify_cached is not None and not args.paths:
            manifest = verify_cached_runtime(args.verify_cached)
        elif args.verify_cached is None and len(args.paths) == 3:
            manifest = materialize_runtime(*args.paths)
        else:
            parser.error("use PROJECT_ROOT STAGING_RUNTIME FINAL_RUNTIME, or --verify-cached RUNTIME")
    except Exception as exc:
        raise SystemExit(f"Runtime data installation failed: {exc}") from exc
    print(f"Verified private data for runtime {manifest['runtimeVersion'][:16]}.")


if __name__ == "__main__":
    main()
