# Data preparation with SpliceImpactR

The shareable browser keeps scientific inputs out of the repository. `scripts/prepare_spliceimpactr_cache.R` creates the exact cache contract expected by the Python builder.

## Pinned sources

- SpliceImpactR from Bioconductor (the current release is 1.0.0 in Bioconductor 3.23/R 4.6; the generated manifest records the installed version).
- Main setup profiles: human v45/111 and mouse M34/111 (raw GTF, transcript FASTA and translated-protein FASTA). The newer human v50/116 and mouse M39/116 profiles remain experimental; their full-build gates have not passed.
- ELM for public validated motif instances, mapped/sequence-confirmed by the
  preparation adapter and normalized with SpliceImpactR.
- Optional Ensembl release 115 GRCh38.p14 top-level reference FASTA for byte-range serving. The builder checks the reference SHA-256 and `.fai` index against the values in `backend/builder/constants.py` when this input is supplied.

When raw inputs are absent, the public `SpliceImpactR::get_annotation()` accession
API downloads the profile's official assets. Public BiocFileCache metadata is
used to recover the original files, which are checksum-verified and copied
unchanged; the filtered processed object is discarded. Existing verified raw
files are reused first. The complete-model adapter reads the GTF with
public `rtracklayer` APIs and the protein FASTA with `Biostrings`, then calls
the release-pinned feature adapter and SpliceImpactR's public
`get_manual_features()` API. It does not use package
internals or vendor SpliceImpactR source. Existing files can be supplied with
all three of `--gtf`, `--transcript-fa`, and `--protein-fa`.

## Annotation is not filtered

Every source gene/transcript model is retained: human v45 has 63,187 genes and
252,930 transcripts; mouse M34 has 57,126 genes and 149,076 transcripts.
TSL 1–5, unscored/NA values, all biotypes, and
`cds_start_NF`/`cds_end_NF` models are included. A SHA-256 of the complete sorted
transcript inventory is compared with the builder's independently imported
inventory. TSL and CDS-completeness flags are metadata, not selection rules.

Do not substitute the processed `SpliceImpactR::get_annotation()` object here. Its analysis defaults
select TSL 1–3 and exclude incomplete CDS rows, and its explicit 1–5 selector
still does not include unscored models. The browser adapter has no TSL selector.

Protein-feature coverage does not define model coverage. SpliceImpactR 1.0.0's
own BioMart helper selects `protein_coding` and relies on automatic archive
discovery. The browser instead connects to the explicit, registry-verified
profile-matched archive with public biomaRt APIs and no TSL/biotype selector. It
processes these query results through public `get_manual_features()`. ELM
requires mapped, sequence-confirmed instances. Original amino-acid intervals and
distinct coincident feature accessions are restored after public normalization,
preventing upstream coordinate clipping and accession collapse. Noncoding,
feature-empty, missing-sequence, and partial-CDS transcripts
stay in the catalog. Runtime genomic features are drawn only when the builder
can establish an exact translation/CDS map. The optional exon audit does not
determine browser geometry.

The documented BioMart `Mart` class and `useDataset()` API validate the explicit
dataset without discovering archives through the current Ensembl website.
This compatibility path does not patch package namespaces or fall back to a
different release. The public manual-feature processor has a minus-strand
bounding-name defect in SpliceImpactR 1.0.0; the browser omits those names and
recomputes exact geometry independently. No incorrect upstream bounding span
is substituted for the raw-GTF coding map.

ELM's documented endpoints used by SpliceImpactR 1.0.0 are HTTP. They carry no
private data/credentials; actual download SHA-256s are recorded, but these are
integrity receipts, not authenticated official signatures. Verify upstream
terms and data provenance before redistributing scientific outputs.

The seven source tables map to browser lanes as follows:

| SpliceImpactR source | Browser interpretation |
| --- | --- |
| `interpro` | InterPro domains/families |
| `pfam` | Pfam domains |
| `cdd` | NCBI CDD conserved domains |
| `tmhmm` | Transmembrane-helix prediction class |
| `signalp` | Signal-peptide prediction class |
| `mobidblite` | Disorder prediction class |
| `elm` | ELM short linear motifs |

The browser keeps source identity and retrieval method visible. It does not turn a Pfam, CDD, or InterPro row into a prediction class merely because it has a domain-like name.

## Install and run

### System prerequisites

Install Python 3.9–3.14, Node.js 22.13+ and R 4.6+ before running
`./scripts/setup_local.sh`. Setup uses pnpm 11.7+ if installed, or a pinned
pnpm through `npx`; a global pnpm installation is not required.

On Ubuntu/Debian or WSL2 Ubuntu, install the R source-build prerequisites first:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends -y \
  build-essential gfortran cmake pkg-config \
  libcurl4-openssl-dev libssl-dev libxml2-dev libpng-dev \
  zlib1g-dev libbz2-dev liblzma-dev
```

Other Linux distributions need their corresponding development packages;
do not use this command on macOS. Missing `curl/curl.h` or `png.h` prevents
R dependencies from compiling. A Conda/source-built R installation on macOS
may also need its matching compiler toolchain and CMake, including for `nloptr`.

If no existing R library is writable, the installer creates R's configured
personal library. Set `R_LIBS_USER` before setup to choose an isolated library,
and use the same setting for preparation and builds. R is needed for data
preparation/building, not for normal browser use.

### SpliceImpactR and annotation inputs

Use the R/Bioconductor release required by the package. The current Bioconductor release lists SpliceImpactR for R 4.6. On a machine with R installed:

```bash
./scripts/install_spliceimpactr.sh
Rscript scripts/prepare_spliceimpactr_cache.R \
  --output data/cache \
  --base-dir data/spliceimpactr-cache
```

The installer delegates to `BiocManager::install("SpliceImpactR")`, which selects the Bioconductor repository compatible with the installed R release and installs declared imports. The browser runtime itself requires only the generated SQLite build and Python/frontend dependencies.

There is no `--filter-tsl` flag. `--force` refreshes protein-feature queries and
rewrites their RDS outputs, without changing model coverage.

Each completed source has a signature/digest receipt. Rerunning resumes verified
sources; changing the input, package version, adapter code, or a source's bytes
invalidates its receipt. Legacy filtered RDS outputs without matching receipts
are rebuilt. The final v3 preparation manifest includes dataset identity and
explicit availability/status/reason for every source. Missing provider attributes
are recorded as unavailable; successfully queried empty coverage is distinct.
A failed remote query blocks completion, never silently becoming an empty result.

The exon-level audit table is generated by default. Add `--skip-exon` when only the seven builder inputs are needed and memory is constrained.

If the raw GENCODE files have already been downloaded by another workflow, avoid a second network request:

```bash
Rscript scripts/prepare_spliceimpactr_cache.R \
  --output data/cache \
  --base-dir data/spliceimpactr-cache \
  --gtf /path/to/gencode.v45.annotation.gtf.gz \
  --transcript-fa /path/to/gencode.v45.pc_transcripts.fa.gz \
  --protein-fa /path/to/gencode.v45.pc_translations.fa.gz
```

The script also derives `exon_features.rds` with `SpliceImpactR::get_exon_features()` for an exon-level audit/provenance view. The browser builder does not trust that derived table as its source of geometry; it recomputes its own projections from the raw GTF and seven feature tables. The generated `spliceimpactr_manifest.json` contains relative filenames, release identifiers, installed versions, the complete inventory, no-filter policy, feature counts, and input digests. It deliberately omits usernames, absolute paths, host details, timestamps, and cache internals.

Raw GENCODE release identity is verified against official-file MD5 pins.
Generated RDS SHA-256s are integrity receipts for this preparation, not official
database signatures or one developer's required serialization. The builder
compares actual imported source counts with those receipts and records them in
its immutable build identity. Feature results may change after an explicit
refresh (especially ELM); archive your local build and receipts when publishing
analyses. Source counts alone do not prove complete remote feature coverage.

## Optional reference FASTA

Transcript, transcript-sequence, and protein-feature browsing does not require a whole-genome reference. To enable optional byte-range reference serving, download the Ensembl release-115 GRCh38.p14 `Homo_sapiens.GRCh38.dna.toplevel.fa`, decompress it, and build the adjacent index:

```bash
mkdir -p data/reference
# obtain the official file from Ensembl release 115
samtools faidx data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa
shasum -a 256 data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa
```

When supplied, the SHA-256 must match `REFERENCE_FASTA_SHA256` and the index digest must match `REFERENCE_FAI_SHA256` in the constants module. The builder refuses a different assembly or index instead of producing a misleading reference endpoint. If no reference is supplied, omit `--reference-fasta`; the full annotation package remains valid and starts without reference-range capability.

## Build and verify

```bash
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache --scope full

# Or, if a reference has been prepared, use this alternative build command:
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache \
  --reference-fasta data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa \
  --scope full
```

The builder's validation gates run during either build command. The separate
`./scripts/verify_release.sh` is a release-candidate check, not the next step
after a single first build: it requires a two-build determinism receipt. Follow
the complete [testing instructions](testing.md#5-full-build-and-release-checks)
to create that receipt and run the release gate.

Once the build is published, copy or archive the resulting `data/builds/<build-id>` locally. Keep it out of GitHub unless a separate data-release policy and licensing review authorizes distribution.

## Prepared input contract

The selected dataset's cache contains the official comprehensive GTF,
protein-coding transcript and translation FASTA files, seven source tables
(`interpro.rds`, `pfam.rds`, `cdd.rds`, `tmhmm.rds`, `signalp.rds`,
`mobidblite.rds`, `elm.rds`), source receipts and
`spliceimpactr_manifest.json`. `exon_features.rds` is an optional audit output.
See [dataset locations](genome_datasets.md) for each cache/build directory.

Each source feature table has these columns:

```text
ensembl_transcript_id  start  stop  chr  strand  feature_id
clean_name  alt_name  database  ensembl_peptide_id  method  name
```

Protein intervals are 1-based inclusive amino-acid coordinates. SQLite/API
genomic geometry is 0-based half-open; visible labels use 1-based inclusive
coordinates. See the [coordinate contract](coordinate_contract.md).

## Optional human PPI context

After building human v45 and installing SpliceImpactR:

```bash
Rscript --vanilla scripts/export_ppi_context.R \
  --dataset human-gencode-v45 \
  --annotation-manifest data/builds/gencode_v45/manifest.json \
  --output data/cache/ppi_export_human_v45

.venv/bin/python -m backend.builder.ppi_context \
  --dataset human-gencode-v45 \
  --source data/cache/ppi_export_human_v45
```

Restart the server afterward. Rebuild a Mac runtime to include this optional
context. The exporter uses the public `SpliceImpactR::get_ppi_interactions()`
resource; the importer creates a separate immutable sidecar in
`data/ppi_context/<dataset-id>/` bound to the exact annotation build. It never
modifies the annotation database or replaces an existing sidecar. Generated
interaction data is ignored by Git and is not bundled with the source.

Compare displays recorded gene partners, BioGRID/DDI/DMI context and exact
focal-side feature observations. Partner-side requirements remain separate;
aggregated feature lists are not reconstructed as paired mechanisms. The
static resource's network date and Ensembl-release correspondence are unknown;
its package/data hashes are separate from annotation-build identity. Human
interaction data is never applied to mouse.

Interaction-switch predictions are disabled because the published
`get_ppi_switches()` implementation can count a changed token on the partner
side against the focal gene. This does not mean transcript domains or GTF
models are misassigned. The browser neither patches nor vendors SpliceImpactR,
and does not present context as interaction gain/loss, confidence or affinity.
See [methodology review](review_log.md) and [known limitations](limitations.md).
