#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
CACHE="data/cache"
QUERY_CACHE="data/spliceimpactr-cache"
DATASET="human-gencode-v45"
CACHE_SET=0
QUERY_CACHE_SET=0
START=1
EXON_AUDIT=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start) START=0; shift ;;
    --with-exon-audit) EXON_AUDIT=1; shift ;;
    --force-features) FORCE=1; shift ;;
    --dataset|--cache|--query-cache)
      [[ $# -gt 1 && "$2" != --* ]] || { echo "Missing value for $1" >&2; exit 2; }
      if [[ "$1" == --dataset ]]; then DATASET="$2";
      elif [[ "$1" == --cache ]]; then CACHE="$2"; CACHE_SET=1;
      else QUERY_CACHE="$2"; QUERY_CACHE_SET=1; fi
      shift 2 ;;
    --help|-h)
      printf '%s\n' 'Usage: ./scripts/setup_local.sh [--no-start] [--with-exon-audit]' \
        '       [--dataset ID] [--cache DIR] [--query-cache DIR] [--force-features]' \
        'Reviewed IDs: human-gencode-v45 (default), human-gencode-v50, mouse-gencode-m39.' \
        'Installs project dependencies, prepares all models in the selected annotation, builds,' \
        'and starts the local browser. Requires Python >=3.9, Node >=22.13, R >=4.6,' \
        'and a network connection for the first setup. Relative paths use the repo root.'
      exit 0 ;;
    *) echo "Unknown argument: $1 (use --help)" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
for command in "$PYTHON_BIN" node Rscript; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing prerequisite: $command. See README.md Requirements." >&2; exit 1; }
done
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else "Python >=3.9 is required")'
CACHE_SUBDIR="$("$PYTHON_BIN" -c 'import sys; from backend.datasets import get_dataset_profile; print(get_dataset_profile(sys.argv[1])["cache_subdir"])' "$DATASET")"
if [[ "$DATASET" != "human-gencode-v45" ]]; then
  if [[ "$CACHE_SET" -eq 0 ]]; then CACHE="data/cache/$CACHE_SUBDIR"; fi
  if [[ "$QUERY_CACHE_SET" -eq 0 ]]; then QUERY_CACHE="data/spliceimpactr-cache/$CACHE_SUBDIR"; fi
fi
node -e 'const v=process.versions.node.split(".").map(Number); if(v[0]<22 || (v[0]===22 && v[1]<13)) {console.error("Node >=22.13 is required"); process.exit(1)}'
Rscript --vanilla -e 'if (getRversion() < "4.6.0") stop("Install R >=4.6 for the released Bioconductor SpliceImpactR package.")'

echo '[1/5] Python environment'
if [[ ! -x .venv/bin/python ]]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -m pip install --disable-pip-version-check --requirement requirements.lock

echo '[2/5] Frontend dependencies and production build'
pnpm_local() {
  if command -v pnpm >/dev/null 2>&1 && node -e 'const v=process.argv[1].split(".").map(Number); process.exit(v[0]>11 || (v[0]===11 && v[1]>=7) ? 0 : 1)' "$(pnpm --version)"; then
    pnpm "$@"
  else
    # No global package-manager installation or administrator access needed.
    command -v npx >/dev/null 2>&1 || { echo 'Install pnpm >=11.7 or a Node installation containing npm/npx.' >&2; exit 1; }
    npx --yes pnpm@11.7.0 "$@"
  fi
}
(
  cd frontend
  pnpm_local install --frozen-lockfile
  pnpm_local run build
)

echo '[3/5] Released Bioconductor dependencies'
./scripts/install_spliceimpactr.sh

echo '[4/5] Complete annotation and protein-feature preparation'
PREPARE=(--dataset "$DATASET" --output "$CACHE" --base-dir "$QUERY_CACHE")
if [[ "$EXON_AUDIT" -eq 0 ]]; then PREPARE+=(--skip-exon); fi
if [[ "$FORCE" -eq 1 ]]; then PREPARE+=(--force); fi
Rscript --vanilla scripts/prepare_spliceimpactr_cache.R "${PREPARE[@]}"

echo '[5/5] Full immutable annotation build'
PYTHON="$ROOT/.venv/bin/python" ./scripts/build_annotations.sh "$CACHE" --dataset "$DATASET" --scope full
if [[ "$START" -eq 1 ]]; then
  exec ./run_local.sh --dataset "$DATASET"
fi
echo "Setup complete. Start the browser with ./run_local.sh --dataset $DATASET"
