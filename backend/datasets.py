"""Versioned dataset contracts shared by Python and the R preparation adapter.

Profiles are deliberately a closed allow-list. A new release must be verified
and added explicitly; numeric release guesses or latest-service fallbacks are
not valid scientific provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping


PROFILE_PATH = Path(__file__).resolve().parent / "data" / "dataset_profiles.json"
DEFAULT_DATASET_ID = "human-gencode-v45"


@dataclass(frozen=True)
class DatasetProfile:
    values: Mapping[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.values["dataset_id"])

    @property
    def release_label(self) -> str:
        release = str(self.values["gencode_release"])
        return "GENCODE " + (release if release.startswith("M") else "v" + release)

    @property
    def contigs(self) -> Mapping[str, int]:
        return self.values["contigs"]

    @property
    def required_inputs(self) -> dict[str, str]:
        return {value["file"]: value["md5"] for value in self.values["raw_inputs"].values()}

    @property
    def feature_provider(self) -> str:
        return f"explicit-release-{self.values['ensembl_release']}-archive/public-biomaRt"

    def filename(self, kind: str) -> str:
        return str(self.values["raw_inputs"][kind]["file"])

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


@lru_cache(maxsize=1)
def dataset_profiles() -> dict[str, DatasetProfile]:
    document = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if document.get("schema") != "transcript-browser-dataset-profiles/v1":
        raise ValueError("Unsupported dataset profile schema")
    result: dict[str, DatasetProfile] = {}
    for value in document["profiles"]:
        profile = DatasetProfile(value)
        if profile.dataset_id in result:
            raise ValueError("Duplicate dataset profile")
        if profile["species"] not in {"human", "mouse"}:
            raise ValueError("Unsupported species in dataset profile")
        if profile["biomart"]["registry_database"] != f"ensembl_mart_{profile['ensembl_release']}":
            raise ValueError("Dataset feature release registry mismatch")
        if not profile.contigs or any(type(length) is not int or length <= 0 for length in profile.contigs.values()):
            raise ValueError("Dataset must provide verified assembly contig lengths")
        result[profile.dataset_id] = profile
    if document["default_dataset_id"] != DEFAULT_DATASET_ID or DEFAULT_DATASET_ID not in result:
        raise ValueError("Dataset default profile mismatch")
    return result


def get_dataset_profile(dataset_id: str | None = None) -> DatasetProfile:
    identifier = dataset_id or DEFAULT_DATASET_ID
    try:
        return dataset_profiles()[identifier]
    except KeyError as exc:
        raise ValueError(f"Unknown dataset {identifier!r}; supported profiles: {', '.join(dataset_profiles())}") from exc


def profile_for_metadata(metadata: Mapping[str, Any], *, legacy_v45: bool = False) -> DatasetProfile:
    """Validate a complete species/release/assembly tuple; legacy means v45 only."""

    identifiers = [metadata[key] for key in ("dataset_id", "datasetId") if key in metadata]
    identifier = identifiers[0] if identifiers else None
    if any(value != identifier for value in identifiers):
        raise ValueError("Conflicting dataset identifier aliases in metadata")
    if identifier is None:
        if not legacy_v45:
            raise ValueError("Dataset metadata is missing dataset_id")
        identifier = DEFAULT_DATASET_ID
    profile = get_dataset_profile(str(identifier))
    releases = [metadata[key] for key in ("release", "gencode_release", "gencodeRelease") if key in metadata]
    if not releases or any(str(release) not in {str(profile["gencode_release"]), profile.release_label} for release in releases):
        raise ValueError(f"Dataset {profile.dataset_id} release is {releases!r}; expected {profile.release_label}")
    ensembl_releases = [metadata[key] for key in ("ensembl_release", "ensemblRelease") if key in metadata]
    if not ensembl_releases or any(str(ensembl) != str(profile["ensembl_release"]) for ensembl in ensembl_releases):
        raise ValueError(f"Dataset {profile.dataset_id} must pair {profile.release_label} with Ensembl {profile['ensembl_release']}")
    if metadata.get("assembly") != profile["assembly"]:
        raise ValueError(f"Dataset {profile.dataset_id} requires assembly {profile['assembly']}")
    species = metadata.get("species")
    if species is None and legacy_v45 and profile.dataset_id == DEFAULT_DATASET_ID:
        species = "human"
    if species != profile["species"]:
        raise ValueError(f"Dataset {profile.dataset_id} requires species {profile['species']}")
    return profile
