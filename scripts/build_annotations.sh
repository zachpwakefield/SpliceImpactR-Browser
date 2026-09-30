#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -eq 0 || "$1" == --* ]]; then
  cat >&2 <<'USAGE'
Usage: ./scripts/build_annotations.sh CACHE_DIR [--reference-fasta PATH] [builder options]

CACHE_DIR must contain the selected profile's raw GTF/FASTA files and seven
RDS protein-feature tables. Use --dataset mouse-gencode-m34 for the matching
mouse annotation; the default is human-gencode-v45. Other reviewed presets
are described in docs/genome_datasets.md.
The optional PATH is a checksum-pinned local Ensembl FASTA matching the
selected assembly; its .fai index must be next to it. Both paths are
intentionally supplied by the caller so this script never embeds a
workstation-specific location.
USAGE
  exit 2
fi
CACHE_DIR="$1"
shift

cd "$PROJECT_ROOT"
exec "${PYTHON:-python3}" -m backend.builder.build \
  --source "$CACHE_DIR" \
  --output-root "$PROJECT_ROOT/data/builds" \
  "$@"
