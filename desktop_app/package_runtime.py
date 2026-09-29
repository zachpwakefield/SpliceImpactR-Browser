#!/usr/bin/env python3
"""Package code/dependencies; declare, but never ZIP, multi-GB scientific files.

The generated archive/manifest are private to this installation. They record
its local interpreter and data sources and must not be uploaded as releases.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys
import sysconfig
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_app.runtime_support import PACKAGE, SCHEMA, canonical_json, file_sha256, runtime_version, validate_manifest


def _tree(source: Path, destination: str) -> dict[str, Path]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"Missing regular runtime directory: {source.name}")
    files: dict[str, Path] = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_symlink():
            raise ValueError(f"Unexpected runtime-source symlink: {destination}/{relative.as_posix()}")
        if path.is_file():
            files[f"{destination}/{relative.as_posix()}"] = path
    return files


def build_runtime(project_root: Path, archive: Path, *, site_packages: Path | None = None) -> dict:
    from backend.app.main import create_app

    root = project_root.expanduser().resolve()
    app = create_app(project_root=root, full_database_verify=True, full_reference_verify=True)
    package = app.state.runtime_package
    if package.technical_preview:
        raise ValueError("The Mac launcher requires a verified full annotation build, not a fixture.")
    files = _tree(root / "backend/app", "backend/app")
    files["backend/__init__.py"] = root / "backend/__init__.py"
    files.update(_tree(root / "frontend/dist", "frontend/dist"))
    files.update(_tree(site_packages or Path(sysconfig.get_paths()["purelib"]), "site-packages"))
    for name in ("manifest.json", "validation_report.json", "build_metrics.json", "determinism_receipt.json"):
        path = package.root / name
        if path.is_symlink():
            raise ValueError(f"Unexpected metadata symlink: {name}")
        if path.is_file():
            files[f"{PACKAGE}/{name}"] = path
    metadata = lambda path: {"size": path.stat().st_size, "sha256": file_sha256(path)}
    database = package.database.path
    external = {f"{PACKAGE}/annotation.sqlite": {**metadata(database), "source": str(database), "kind": "database"}}
    reference = None
    if package.reference is not None:
        ref = package.reference
        if not ref.fai_public_name:
            raise ValueError("The optional reference needs a declared FAI index; rebuild it using docs/reference_setup.md.")
        keys = {"fasta": ref.primary_public_name, "index": ref.fai_public_name, "chrom_sizes": ref.chrom_sizes_public_name}
        if ref.gzi_public_name:
            keys["gzi"] = ref.gzi_public_name
        extra = set(ref.allowed_files) - set(keys.values())
        if len(extra) > 1:
            raise ValueError("Optional reference contains undeclared extra artifacts; rebuild using the documented reference adapter.")
        if extra:
            keys["aliases"] = next(iter(extra))
        directory = ref.root.relative_to(package.root).as_posix()
        outer_reference = package.manifest.get("reference") or {}
        reference = {"directory": f"{PACKAGE}/{directory}", "manifestName": str(outer_reference.get("manifest", "reference_manifest.json")), "keys": keys}
        for name, path in sorted(ref.allowed_files.items()):
            relative = f"external-files/reference/{name}"
            external[relative] = {"source": str(path), "size": path.stat().st_size, "sha256": ref.checksums[name], "kind": "reference", "publicName": name}
        # Replace reference metadata during materialization; old identity
        # receipts/absolute symlinks must never accompany a copied reference.
    manifest = {
        "schema": SCHEMA,
        "buildHash": package.build_hash,
        "pythonExecutable": str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
        "pythonVersion": platform.python_version(),
        "architecture": platform.machine(),
        "bundledFiles": {name: metadata(path) for name, path in sorted(files.items())},
        "externalFiles": external,
        "reference": reference,
        "frontendIndexSha256": metadata(root / "frontend/dist/index.html")["sha256"],
    }
    manifest["runtimeVersion"] = runtime_version(manifest)
    validate_manifest(manifest)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.is_symlink():
        raise ValueError("The runtime archive destination must not be a symlink.")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, path in sorted(files.items()):
            output.write(path, name)
        output.writestr("runtime-manifest.json", canonical_json(manifest))
    archive.with_name("Runtime-manifest.json").write_bytes(canonical_json(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        manifest = build_runtime(args.project_root, args.archive)
    except Exception as exc:
        raise SystemExit(f"Runtime packaging failed: {exc}") from exc
    print(f"Packaged local runtime {manifest['runtimeVersion'][:16]} for annotation {manifest['buildHash'][:16]}.")


if __name__ == "__main__":
    main()
