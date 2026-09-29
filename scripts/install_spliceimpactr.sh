#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
command -v Rscript >/dev/null 2>&1 || { echo "Install R 4.6 (or a later release supported by Bioconductor) first: https://cran.r-project.org/" >&2; exit 1; }

# SpliceImpactR is a Bioconductor dependency, not vendored application code.
# BiocManager selects the compatible Bioconductor repository for the installed
# R release and installs the package's declared imports as needed.
exec Rscript --vanilla -e '
if (getRversion() < "4.6.0") {
  stop("The released Bioconductor SpliceImpactR package needs the R 4.6/Bioconductor 3.23 installation path. Install R 4.6 or later, then rerun this script.")
}
source(commandArgs(trailingOnly = TRUE)[[1L]])
ensure_browser_r_library()
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager", repos = "https://cloud.r-project.org")
}
BiocManager::install(c("SpliceImpactR", "jsonlite", "digest"), ask = FALSE, update = FALSE)
if (!requireNamespace("SpliceImpactR", quietly = TRUE)) {
  stop("Bioconductor installation completed without an available SpliceImpactR package.")
}
if (utils::packageVersion("SpliceImpactR") < "1.0.0") {
  stop("A development SpliceImpactR version was found. Install the released Bioconductor package (>= 1.0.0).")
}
cat("Installed SpliceImpactR", as.character(utils::packageVersion("SpliceImpactR")), "\n")
' "$ROOT/r/library_setup.R"
