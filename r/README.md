# Annotation-build R environment

R is used only during data preparation and to read/normalize the seven local
feature RDS files. It is not required by the browser at runtime.

SpliceImpactR is installed from Bioconductor with:

```bash
./scripts/install_spliceimpactr.sh
```

The current Bioconductor release lists SpliceImpactR for R 4.6. Bioconductor
selects the compatible package repository for the R version in use. The
adapter records the installed SpliceImpactR and Bioconductor versions in its
relative-path preparation manifest.

`library_setup.R` ensures non-interactive installation has a writable library,
creating R's configured personal library when necessary. Use the same
`R_LIBS_USER` setting for installation, preparation, and export/build commands
when an isolated library is selected.

`browser_annotation.R` reads every model in the raw GTF with public
`rtracklayer`/`Biostrings` APIs. It keeps TSL 1–5 and unscored values, all biotypes,
and incomplete CDS models. This bypasses the filtering in the package's
analysis-oriented `get_annotation()` without calling private package functions.
`archive_features.R` queries the explicit Ensembl 111 archive with public
biomaRt APIs, verifies its registry release, and applies no TSL/biotype query
selector. It uses the documented `Mart` connection class to avoid broken
automatic archive discovery and processes results with the released
SpliceImpactR public `get_manual_features()` API. No private APIs or namespace
patches are used. ELM instances are mapped/sequence-confirmed; the optional
exon audit uses public `get_exon_features()`. Source-specific coverage and the
upstream bounding-label limitation are documented in the main README.

`preflight.R` checks the exporter minimums in `requirements.tsv` (R >=4.5,
data.table >=1.14, jsonlite >=1.8). The recommended R 4.6 installation satisfies
this contract; no second R version or obsolete exact patch pin is required.
Actual package versions are recorded in preparation/export manifests. The
builder checks source integrity, complete model inventory, source counts, and
scientific geometry independently of RDS serialization bytes.

Run the offline synthetic/public-API integration test with:

```bash
Rscript --vanilla tests/r/test_browser_annotation.R
```

Dependency acquisition may require a network connection. Once those packages
and the audited local inputs exist, annotation building and browser runtime do
not fetch remote data.
