# R preparation adapter

R is needed for data preparation, not browser runtime. Install the released
Bioconductor package and preparation dependencies with R 4.6+:

```bash
./scripts/install_spliceimpactr.sh
```

The adapter keeps the complete raw GTF instead of using SpliceImpactR's
analysis-oriented transcript filtering. It queries the selected release's
Ensembl archive with public biomaRt APIs and processes features through
SpliceImpactR's public `get_manual_features()` API. Optional exon auditing uses
`get_exon_features()`. No package source is vendored or patched.

| File | Purpose |
| --- | --- |
| `browser_annotation.R` | Raw transcript/sequence import and feature normalization |
| `archive_features.R` | Release-matched feature queries and ELM sequence checks |
| `datasets.R` | Shared species/release profiles and raw-file validation |
| `export_features.R` | Builder-readable export of prepared RDS tables |
| `library_setup.R`, `preflight.R` | Writable-library and dependency checks |

When using an isolated R library, set the same `R_LIBS_USER` for installation,
preparation and export. Manifests record the package versions and input digests.

Run the offline adapter test from the repository root:

```bash
Rscript --vanilla tests/r/test_browser_annotation.R
```

See [data preparation](../docs/data_preparation.md) for the complete workflow.
