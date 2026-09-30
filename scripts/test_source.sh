#!/usr/bin/env bash
set -euo pipefail

# Run the checks that do not require a generated annotation database.  This is
# intentionally conservative: it never downloads dependencies or writes test
# artefacts into the repository.  Use --require-frontend in CI/release work so
# a missing frontend install is an error rather than a documented skip.

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
VENV_PYTHON="${VENV_PYTHON:-$ROOT/.venv/bin/python}"
REQUIRE_FRONTEND=0
REQUIRE_ALL=0

for argument in "$@"; do
  case "$argument" in
    --require-frontend) REQUIRE_FRONTEND=1 ;;
    --require-all) REQUIRE_FRONTEND=1; REQUIRE_ALL=1 ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./scripts/test_source.sh [--require-frontend | --require-all]

Runs source/privacy checks, builder/data-contract tests, and (when available)
the installed backend and frontend test suites.  It does not build annotation
data and it does not install packages.  Use --require-frontend to fail when
frontend dependencies have not already been installed.
Use --require-all to require backend, frontend, and released R dependencies.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $argument" >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"

echo "[1/5] publication/privacy audit"
./scripts/verify_publication.sh

echo "[2/5] Python syntax"
PY_CACHE="$(mktemp -d "${TMPDIR:-/tmp}/transcript-browser-pycache.XXXXXX")"
cleanup() { rm -rf "$PY_CACHE"; }
trap cleanup EXIT
PYTHONPYCACHEPREFIX="$PY_CACHE" "$PYTHON_BIN" -B -m compileall -q backend scripts tests desktop_app
bash -n desktop_app/build_macos_app.sh desktop_app/install_macos_app.sh

echo "[3/5] data-contract tests"
PYTHONPATH="$ROOT" "$PYTHON_BIN" -B -m unittest discover \
  -s tests/data -p 'test_*.py' -v

echo "[4/5] backend tests (if runtime dependencies are installed)"
if [[ -x "$VENV_PYTHON" ]] && "$VENV_PYTHON" -c 'import fastapi, httpx, pydantic, reportlab' >/dev/null 2>&1; then
  PYTHONPATH="$ROOT" "$VENV_PYTHON" -B -m unittest discover \
    -s backend/tests -p 'test_*.py' -v
else
  if [[ "$REQUIRE_ALL" -eq 1 ]]; then
    echo "ERROR: backend dependencies are missing; install requirements.lock in .venv" >&2
    exit 1
  fi
  echo "SKIP: backend dependencies are not installed at $VENV_PYTHON"
  echo "      Run ./run_local.sh once, or install requirements.lock in a venv."
fi

echo "[5/5] frontend tests/build (if frontend dependencies are installed)"
if [[ -x "$ROOT/frontend/node_modules/.bin/tsx" ]] && command -v pnpm >/dev/null 2>&1; then
  (
    cd "$ROOT/frontend"
    # Newer pnpm releases may auto-install when running scripts. Testing must
    # use the already installed lockfile dependencies, never mutate/download.
    CI=true pnpm --config.verify-deps-before-run=false test
    CI=true pnpm --config.verify-deps-before-run=false run typecheck
    CI=true pnpm --config.verify-deps-before-run=false run build
  )
else
  if [[ "$REQUIRE_FRONTEND" -eq 1 ]]; then
    echo "ERROR: frontend dependencies are missing; run pnpm install --frozen-lockfile" >&2
    exit 1
  fi
  echo "SKIP: frontend dependencies are not installed"
  echo "      In a networked checkout run: cd frontend && pnpm install --frozen-lockfile"
fi

if command -v Rscript >/dev/null 2>&1; then
  Rscript --vanilla -e \
    'invisible(lapply(c("r/export_features.R", "r/preflight.R", "r/datasets.R", "r/browser_annotation.R", "r/archive_features.R", "r/library_setup.R", "scripts/prepare_spliceimpactr_cache.R", "scripts/export_ppi_context.R", "tests/r/test_ppi_context_export.R", "tests/r/test_dataset_release_smoke.R"), function(path) parse(file=path)))' \
    >/dev/null
  echo "R source parse passed."
  if Rscript --vanilla -e 'quit(status=if(all(vapply(c("SpliceImpactR","data.table","jsonlite","digest","rtracklayer","Biostrings"), requireNamespace, logical(1), quietly=TRUE))) 0 else 1)' >/dev/null 2>&1; then
    Rscript --vanilla tests/r/test_browser_annotation.R
    Rscript --vanilla tests/r/test_ppi_context_export.R
  elif [[ "$REQUIRE_ALL" -eq 1 ]]; then
    echo "ERROR: R dependencies missing; run ./scripts/install_spliceimpactr.sh" >&2
    exit 1
  else
    echo "SKIP: complete-annotation R integration test requires installed Bioconductor dependencies."
  fi
else
  if [[ "$REQUIRE_ALL" -eq 1 ]]; then
    echo "ERROR: Rscript missing; install R and the released Bioconductor dependencies" >&2
    exit 1
  fi
  echo "SKIP: Rscript is not installed (R checks run in the R-enabled CI job)."
fi

echo "Available source checks passed (review any SKIP lines). This does not prove a full data build or UI acceptance. See docs/testing.md."
