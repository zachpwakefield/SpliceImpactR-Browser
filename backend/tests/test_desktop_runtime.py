from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_api import make_package, write_manifest
from desktop_app.materialize_runtime_data import materialize_runtime, verify_cached_runtime
from desktop_app.package_runtime import build_runtime
from desktop_app.runtime_support import PACKAGE, canonical_json, file_sha256, runtime_version, safe_child, validate_manifest


class DesktopRuntimeTests(unittest.TestCase):
    def project(self, base: Path, *, reference: bool = False, preview: bool = False) -> tuple[Path, Path]:
        root = base / "arbitrarily-named-checkout"
        root.mkdir()
        package = make_package(root, technical_preview=preview)
        destination = root / PACKAGE
        destination.parent.mkdir(parents=True)
        package.rename(destination)
        for name, text in {
            "backend/__init__.py": "",
            "backend/app/cli.py": "# packaged fixture entry point\n",
            "frontend/dist/index.html": "<html><body>local fixture</body></html>\n",
            "fake-dependencies/uvicorn/__init__.py": "# fixture dependency\n",
            "fake-dependencies/uvicorn/__pycache__/ignored.pyc": "not bundled\n",
        }.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if reference:
            ref = destination / "reference"
            ref.mkdir()
            sources = base / "external-reference"
            sources.mkdir()
            fasta = sources / "whole.fa"
            index = sources / "whole.fa.fai"
            fasta.write_bytes(b">chr12\nACGTACGTACGTACGT\n")
            index.write_bytes(b"chr12\t16\t7\t16\t17\n")
            chrom = ref / "chrom.sizes"
            aliases = ref / "chrom_aliases.tsv"
            chrom.write_bytes(b"chr12\t133275309\n")
            aliases.write_bytes(b"12\tchr12\n")
            files = {"fasta": ("genome.fa", fasta), "index": ("genome.fa.fai", index), "chrom_sizes": (chrom.name, chrom), "aliases": (aliases.name, aliases)}
            declarations, records = {}, []
            for key, (name, path) in files.items():
                stat = path.stat()
                record = {"public_name": name, "link_path": name, "sha256": file_sha256(path), "size": stat.st_size}
                if key in ("fasta", "index"):
                    (ref / name).symlink_to(path)
                    record["target_path"] = str(path)
                declarations[key] = record
                records.append({**record, "path": name, "inode": stat.st_ino, "mtime_ns": stat.st_mtime_ns})
            (ref / "reference_manifest.json").write_bytes(canonical_json({"verified": True, "assembly": "GRCh38.p14", **declarations}))
            (ref / "verification_receipt.json").write_bytes(canonical_json({"files": records}))
            write_manifest(destination, technical_preview=False, reference={"available": True, "verified": True, "directory": "reference", "manifest": "reference_manifest.json"})
        return root, root / "fake-dependencies"

    def bundle(self, base: Path, *, reference: bool = False) -> tuple[Path, Path, Path, dict]:
        root, dependencies = self.project(base, reference=reference)
        archive = base / "app/Runtime.zip"
        manifest = build_runtime(root, archive, site_packages=dependencies)
        staging, final = base / "private-staging", base / "private-runtime"
        with zipfile.ZipFile(archive) as source:
            source.extractall(staging)
        return root, staging, final, manifest

    def test_archive_contains_code_but_not_large_data_or_python_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, dependencies = self.project(base)
            original = file_sha256(root / PACKAGE / "annotation.sqlite")
            archive = base / "app/Runtime.zip"
            manifest = build_runtime(root, archive, site_packages=dependencies)
            validate_manifest(manifest)
            with zipfile.ZipFile(archive) as source:
                names = source.namelist()
                self.assertIn("backend/app/cli.py", names)
                self.assertIn("frontend/dist/index.html", names)
                self.assertIn("runtime-manifest.json", names)
                self.assertFalse(any(name.endswith(".sqlite") or "__pycache__" in name for name in names))
            self.assertEqual(original, file_sha256(root / PACKAGE / "annotation.sqlite"))
            self.assertEqual(json.loads(archive.with_name("Runtime-manifest.json").read_text()), manifest)

    def test_interface_change_versions_runtime_without_changing_annotation_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, dependencies = self.project(base)
            first = build_runtime(root, base / "first/Runtime.zip", site_packages=dependencies)
            (root / "frontend/dist/index.html").write_text("updated interface", encoding="utf-8")
            second = build_runtime(root, base / "second/Runtime.zip", site_packages=dependencies)
            self.assertEqual(first["buildHash"], second["buildHash"])
            self.assertNotEqual(first["runtimeVersion"], second["runtimeVersion"])
            self.assertNotEqual(first["frontendIndexSha256"], second["frontendIndexSha256"])

    def test_private_clone_is_independent_and_original_package_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, staging, final, manifest = self.bundle(Path(temp))
            original = root / PACKAGE / "annotation.sqlite"
            before = (file_sha256(original), original.stat().st_mode)
            materialize_runtime(root, staging, final)
            self.assertFalse(staging.exists())
            clone = final / PACKAGE / "annotation.sqlite"
            self.assertFalse(clone.is_symlink())
            self.assertNotEqual(original.stat().st_ino, clone.stat().st_ino)
            self.assertEqual((file_sha256(original), original.stat().st_mode), before)
            self.assertEqual(verify_cached_runtime(final)["buildHash"], manifest["buildHash"])

    def test_modified_bundled_code_is_rejected_before_data_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, staging, final, _ = self.bundle(Path(temp))
            (staging / "backend/app/cli.py").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                materialize_runtime(root, staging, final)
            self.assertFalse(final.exists())

    def test_same_size_source_change_is_rejected_by_clone_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, staging, final, _ = self.bundle(Path(temp))
            source = root / PACKAGE / "annotation.sqlite"
            contents = source.read_bytes()
            source.write_bytes(contents[:-1] + bytes([contents[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                materialize_runtime(root, staging, final)
            self.assertFalse(final.exists())

    def test_existing_runtime_is_never_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, staging, final, _ = self.bundle(Path(temp))
            final.mkdir()
            sentinel = final / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing runtime"):
                materialize_runtime(root, staging, final)
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_optional_reference_targets_and_identity_receipts_use_final_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, staging, final, _ = self.bundle(Path(temp), reference=True)
            original_manifest = (root / PACKAGE / "manifest.json").read_bytes()
            materialize_runtime(root, staging, final)
            verify_cached_runtime(final)
            link = final / PACKAGE / "reference/genome.fa"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), (final / "external-files/reference/genome.fa").resolve())
            self.assertEqual((root / PACKAGE / "manifest.json").read_bytes(), original_manifest)
            self.assertEqual((final / PACKAGE / "manifest.json").read_bytes(), original_manifest)
            app = create_app(project_root=final, full_reference_verify=True)
            client = TestClient(app, base_url="http://127.0.0.1")
            response = client.get("/reference/genome.fa", headers={"Range": "bytes=7-10"})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b"ACGT")

    def test_runtime_paths_reject_traversal_and_intermediate_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("", ".", "/absolute", "../escape", "nested/../escape", "nested//file"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    safe_child(root, name)
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                safe_child(root, "link/file")

    def test_manifest_identity_and_file_declarations_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, _, _, manifest = self.bundle(Path(temp))
            manifest["buildHash"] = "changed identity"
            with self.assertRaisesRegex(ValueError, "content identity"):
                validate_manifest(manifest)
            manifest["runtimeVersion"] = runtime_version(manifest)
            manifest["externalFiles"]["../escaped.sqlite"] = next(iter(manifest["externalFiles"].values()))
            manifest["runtimeVersion"] = runtime_version(manifest)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
