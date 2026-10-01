# Prepare or reuse annotation data

For a first installation, follow [Install](../README.md#install). The setup
script downloads the data, installs the released Bioconductor SpliceImpactR
package, and builds the browser. Use this guide if you already have annotation
files, want a separate cache, or want human PPI context.

## System prerequisites

Use Python 3.9–3.14, Node.js 22.13+, and R 4.6+. Setup manages pnpm if needed.
R and internet access are needed for preparation; normal browsing uses the
finished local database.

On Ubuntu/Debian or WSL2 Ubuntu, install these R build dependencies first:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends -y \
  build-essential gfortran cmake pkg-config \
  libcurl4-openssl-dev libssl-dev libxml2-dev libpng-dev \
  zlib1g-dev libbz2-dev liblzma-dev
```

Other Linux distributions need equivalent development packages. On macOS,
source-built or Conda R may need its compiler toolchain and CMake. If you use
an isolated R library, set `R_LIBS_USER` consistently for installation and
preparation. The installer otherwise creates a writable personal library.

## Reuse an existing browser cache

A prepared browser cache contains the raw GTF/FASTA files, seven feature RDS
tables, receipts, and `spliceimpactr_manifest.json`. Point setup at that folder:

```bash
./scripts/setup_local.sh --cache /path/to/browser-cache --no-start
./run_local.sh
```

Verified inputs and completed queries are reused. For mouse, add
`--dataset mouse-gencode-m34` to both commands. Keep different releases in
separate caches; see [dataset locations](genome_datasets.md).

## Use downloaded GTF and FASTA files

If another SpliceImpactR workflow downloaded the official files, supply all
three raw inputs rather than its processed annotation object. From the
repository root:

```bash
./scripts/install_spliceimpactr.sh
Rscript --vanilla scripts/prepare_spliceimpactr_cache.R \
  --dataset human-gencode-v45 \
  --output data/cache --base-dir data/spliceimpactr-cache --skip-exon \
  --gtf /path/to/gencode.v45.annotation.gtf.gz \
  --transcript-fa /path/to/gencode.v45.pc_transcripts.fa.gz \
  --protein-fa /path/to/gencode.v45.pc_translations.fa.gz
./scripts/setup_local.sh --cache data/cache --no-start
./run_local.sh
```

The preparation script retrieves InterPro, Pfam, CDD, TMHMM, SignalP,
MobiDB-lite, and ELM features; Ensembl-backed queries use the selected release.
It retains every raw-GTF transcript,
including TSL 1–5, unscored, noncoding, and incomplete-CDS models. SpliceImpactR's
processed annotation defaults are not used to select browser transcripts.
Protein features are projected through the builder's verified coding maps.

Omit `--skip-exon` to also generate SpliceImpactR's exon-level audit table;
the browser does not need that table to draw tracks. Raw file checksums,
release identity, and the complete transcript inventory are checked during
preparation and building.

## Resume, refresh, or rebuild

Rerun the same setup command after an interruption. Completed verified sources
resume; a failed provider request is reported rather than treated as empty
coverage. The first full preparation can require several GB of RAM, so avoid
parallel full-genome builds.

Use `--force-features` with setup only when you want fresh feature queries.
To rebuild a prepared cache without repeating installation or preparation:

```bash
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache --scope full
```

Keep the cache and `data/builds/` locally; generated scientific data is not
part of the GitHub source. A whole-genome FASTA is unnecessary for transcript
or protein browsing; [reference serving](reference_setup.md) is optional.

## Optional human PPI context

After building human v45:

```bash
Rscript --vanilla scripts/export_ppi_context.R \
  --dataset human-gencode-v45 \
  --annotation-manifest data/builds/gencode_v45/manifest.json \
  --output data/cache/ppi_export_human_v45

.venv/bin/python -m backend.builder.ppi_context \
  --dataset human-gencode-v45 \
  --source data/cache/ppi_export_human_v45
```

Restart the server, or reinstall the Mac launcher, to include the new context.
**Compare** will show recorded gene partners and their feature requirements
alongside each isoform's features. This human-only resource comes from public
`SpliceImpactR::get_ppi_interactions()`; interaction-switch predictions are not
enabled. It is stored separately in `data/ppi_context/`, linked to the exact
annotation build.
