# SpliceImpactR preparation dependency

The browser does not vendor SpliceImpactR. Install the Bioconductor package in
the R environment used for one-time data preparation:

```bash
./scripts/install_spliceimpactr.sh
```

This uses `BiocManager::install("SpliceImpactR")` and retains the upstream
GPL-3 attribution through [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
The installed package version and Bioconductor release are recorded in the
generated preparation manifest.

Then, from the repository root, run:

```bash
Rscript scripts/prepare_spliceimpactr_cache.R \
  --output data/cache \
  --base-dir data/spliceimpactr-cache
```

The adapter obtains unmodified GENCODE v45 annotation/sequences and queries
the explicit Ensembl 111 archive without TSL/biotype selectors. Public biomaRt
APIs avoid broken automatic archive discovery; SpliceImpactR's public
`get_manual_features()` processes the query results and `get_exon_features()`
provides the optional exon audit. ELM instances are sequence-confirmed. No
private package calls or vendored source are used. The browser does not import
SpliceImpactR at runtime; it consumes the prepared files after builder
validation. See the main README for feature-coverage/provenance limitations.
