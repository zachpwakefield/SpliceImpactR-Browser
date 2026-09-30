#!/usr/bin/env python3
"""Exercise the read-only API against a running local transcript browser.

This deliberately uses only the Python standard library, so it can be run from
another terminal while the browser server is running. It resolves a gene
from the search index and a translated transcript from that gene's rows,
rather than assuming a particular species or transcript identifier. Each
scientific request is independently scoped when --dataset is supplied.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


class SmokeFailure(RuntimeError):
    pass


def _get(base_url: str, path: str) -> tuple[int, Any]:
    url = base_url.rstrip("/") + path
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            status = int(response.status)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"GET {path} returned HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise SmokeFailure(f"Could not reach {base_url}: {exc.reason}") from exc
    try:
        return status, json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"GET {path} did not return JSON: {body[:500]}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _query(**values: object) -> str:
    return urlencode({key: value for key, value in values.items() if value is not None})


def _dataset_path(path: str, dataset: str | None) -> str:
    """Append one immutable request scope without dropping existing queries."""
    if dataset is None:
        return path
    _require(bool(dataset) and len(dataset) <= 80 and bool(re.fullmatch(r"[A-Za-z0-9_.:-]+", dataset)),
             "dataset must be one safe nonempty identifier")
    parts = urlsplit(path)
    query = parse_qsl(parts.query, keep_blank_values=True)
    existing = [value for key, value in query if key == "dataset"]
    if existing:
        _require(existing == [dataset], "request contains a conflicting or duplicate dataset scope")
        return path
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode([*query, ("dataset", dataset)]), parts.fragment))


def _select_gene(results: list[dict[str, Any]], query: str) -> dict[str, Any]:
    genes = [item for item in results if isinstance(item, dict) and item.get("kind") == "gene"]
    normalized = query.strip().casefold()
    exact = [item for item in genes if any(
        isinstance(item.get(key), str) and item[key].casefold() == normalized
        for key in ("id", "versionedId", "symbol", "label")
    )]
    candidates = exact or genes
    _require(len(candidates) == 1,
             "search did not resolve one unambiguous gene; supply its exact stable ID with --gene-query")
    _require(isinstance(candidates[0].get("id"), str) and bool(candidates[0]["id"]),
             "gene search result has no identifier")
    return candidates[0]


def _has_translation(transcript: dict[str, Any]) -> bool:
    length = transcript.get("proteinLength")
    return isinstance(length, (int, float)) and not isinstance(length, bool) and math.isfinite(length) and length > 0


def _select_transcript(gene: dict[str, Any], requested: str | None) -> str:
    rows = gene.get("transcripts")
    _require(isinstance(rows, list) and bool(rows), "gene has no transcripts")
    _require(all(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] for row in rows),
             "gene transcript inventory is malformed")
    _require(all(row.get("geneId") in (None, gene.get("id")) for row in rows),
             "gene transcript inventory contains a transcript owned by another gene")
    if requested is not None:
        _require(bool(requested.strip()), "--transcript must not be empty")
        normalized = requested.strip().casefold()
        matches = [row for row in rows if any(
            isinstance(row.get(key), str) and row[key].casefold() == normalized
            for key in ("id", "versionedId")
        )]
        _require(len(matches) == 1,
                 f"transcript {requested!r} does not identify one transcript belonging to gene {gene.get('id')!r}")
        selected = matches[0]
        _require(_has_translation(selected), f"transcript {requested!r} has no translated protein to exercise")
    else:
        selected = next((row for row in rows if _has_translation(row)), None)
        _require(selected is not None,
                 f"gene {gene.get('id')!r} has no translated transcript; choose another gene with --gene-query")
    return str(selected["id"])


def _validate_dataset_identity(
    dataset: str,
    catalog: dict[str, Any],
    manifest: dict[str, Any],
    health: dict[str, Any],
) -> None:
    _require(manifest.get("datasetId") == dataset, "manifest returned a different dataset")
    _require(health.get("datasetId") == dataset, "health returned a different dataset")
    _require(health.get("buildHash") == manifest.get("buildHash"), "health and manifest build identities disagree")
    rows = catalog.get("datasets")
    _require(isinstance(rows, list), "dataset catalog has no installed dataset list")
    matching = [row for row in rows if isinstance(row, dict) and row.get("datasetId") == dataset]
    _require(len(matching) == 1, f"dataset {dataset!r} is missing or duplicated in the installed catalog")
    for key in ("buildHash", "species", "assembly", "gencodeRelease", "ensemblRelease"):
        expected, actual = matching[0].get(key), manifest.get(key)
        _require(expected is not None and actual is not None and str(expected) == str(actual),
                 f"catalog and manifest {key} identities disagree")


def run(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")
    dataset = getattr(args, "dataset", None)

    def get(path: str) -> tuple[int, Any]:
        return _get(base_url, _dataset_path(path, dataset))

    status, health = get("/api/v1/health")
    _require(status == 200, f"health returned HTTP {status}")
    _require(health.get("status") == "ok", "health status is not ok")
    _require(health.get("readOnly") is True, "runtime is not marked read-only")

    status, manifest = get("/api/v1/manifest")
    _require(status == 200, f"manifest returned HTTP {status}")
    _require(bool(manifest.get("buildHash")), "manifest has no buildHash")
    _require("capabilities" in manifest, "manifest has no capabilities")
    if dataset is not None:
        # The catalog describes installed contexts and is deliberately global;
        # it must not be accidentally scoped like scientific data requests.
        status, catalog = _get(base_url, "/api/v1/datasets")
        _require(status == 200, f"dataset catalog returned HTTP {status}")
        _validate_dataset_identity(dataset, catalog, manifest, health)
    if args.expect_scope:
        _require(
            manifest.get("scope") == args.expect_scope,
            f"expected scope={args.expect_scope!r}, got {manifest.get('scope')!r}",
        )

    status, search = get(
        "/api/v1/search?" + _query(q=args.gene_query, limit=50),
    )
    _require(status == 200, f"search returned HTTP {status}")
    results = list(search.get("results") or [])
    _require(results, f"search returned no results for {args.gene_query!r}")
    gene_result = _select_gene(results, args.gene_query)

    gene_id = str(gene_result["id"])
    status, gene = get("/api/v1/genes/" + quote(gene_id, safe=""))
    _require(status == 200, f"gene endpoint returned HTTP {status}")
    _require(gene.get("id") == gene_id, "gene endpoint returned a different gene")
    transcript_id = _select_transcript(gene, args.transcript)

    # The region response is the genome-browser contract: it must carry both
    # genes and transcript rows for a real locus, not only a detail endpoint.
    chromosome = gene.get("chr")
    start0 = gene.get("start0")
    end0 = gene.get("end0")
    _require(chromosome and isinstance(start0, int) and isinstance(end0, int), "gene has no locus")
    status, region = get(
        "/api/v1/region?" + _query(chr=chromosome, start0=start0, end0=end0, detail="expanded"),
    )
    _require(status == 200, f"region returned HTTP {status}")
    _require(len(region.get("genes") or []) > 0, "region returned no genes")
    _require(len(region.get("transcripts") or []) > 0, "region returned no transcripts")

    status, transcript = get("/api/v1/transcripts/" + quote(transcript_id, safe=""))
    _require(status == 200, f"transcript endpoint returned HTTP {status}")
    _require(transcript.get("id") == transcript_id, "transcript endpoint returned a different transcript")
    _require(transcript.get("geneId") == gene_id, "transcript endpoint returned a transcript owned by another gene")

    status, features = get(
        "/api/v1/transcripts/"
        + quote(transcript_id, safe="")
        + "/features?"
        + _query(sources=args.feature_sources),
    )
    _require(status == 200, f"feature endpoint returned HTTP {status}")
    _require(features.get("transcriptId") == transcript_id, "feature response has wrong transcript")
    _require("features" in features and "mapping" in features, "feature response is incomplete")

    status, sequence = get(
        "/api/v1/transcripts/"
        + quote(transcript_id, safe="")
        + "/sequence?kind=protein",
    )
    _require(status == 200, f"sequence endpoint returned HTTP {status}")
    _require(sequence.get("kind") == "protein", "sequence response is not protein")
    _require(sequence.get("available") is True, "protein sequence is not available")
    _require(int(sequence.get("length") or 0) > 0, "protein sequence is empty")

    print("API smoke test passed")
    print(json.dumps({
        "datasetId": manifest.get("datasetId"),
        "species": manifest.get("species"),
        "release": manifest.get("release"),
        "assembly": manifest.get("assembly"),
        "buildHash": manifest.get("buildHash"),
        "scope": manifest.get("scope"),
        "gene": gene_id,
        "transcript": transcript_id,
        "featureCount": len(features.get("features") or []),
        "proteinLength": sequence.get("length"),
    }, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", help="Installed dataset ID; scopes every scientific API request independently.")
    parser.add_argument("--gene-query", default="SP1")
    parser.add_argument(
        "--transcript",
        default=None,
        help="Transcript stable or exact versioned ID belonging to the selected gene (default: its first translated row).",
    )
    parser.add_argument(
        "--feature-sources",
        default="interpro,pfam,mobidblite,elm",
        help="Comma-separated feature sources sent to the API.",
    )
    parser.add_argument(
        "--expect-scope",
        default="sp1",
        help="Expected manifest scope; pass an empty string to skip this assertion.",
    )
    args = parser.parse_args()
    if args.expect_scope == "":
        args.expect_scope = None
    try:
        run(args)
    except SmokeFailure as exc:
        print(f"API smoke test failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
