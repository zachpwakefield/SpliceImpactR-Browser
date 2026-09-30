#!/usr/bin/env python3
"""Explicit test-only server: tiny API contracts, not scientific annotations."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import uvicorn

from backend.app.main import create_app
from backend.datasets import dataset_profiles
from backend.tests.test_datasets import synthetic_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1–65535")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        parser.error("Build frontend/dist before running this optional UI test server.")
    print("TEST ONLY: synthetic dataset contracts, not a biological installation.", flush=True)
    with tempfile.TemporaryDirectory(prefix="transcript-browser-ui-fixtures-") as directory:
        root = Path(directory)
        for identifier in dataset_profiles():
            synthetic_dataset(root, identifier)
        shutil.copytree(ROOT / "frontend" / "dist", root / "frontend" / "dist")
        app = create_app(project_root=root, dataset="human-gencode-v45")
        uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
