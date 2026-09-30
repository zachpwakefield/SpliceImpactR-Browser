# Genome datasets and release validation

An annotation is a complete immutable scientific dataset, not a species label
applied to an existing database. Selection is independent in each tab. Missing,
invalid and unknown selections fail explicitly; another release or a human
fixture is never silently substituted for mouse.

## Reviewed profiles

| ID | GENCODE / Ensembl | Assembly | Cache | Build directory |
| --- | --- | --- | --- | --- |
| `human-gencode-v45` | v45 / 111 | GRCh38.p14 | `data/cache` | `data/builds/gencode_v45` |
| `human-gencode-v50` | v50 / 116 | GRCh38.p14 | `data/cache/human_gencode_v50` | `data/builds/human_gencode_v50` |
| `mouse-gencode-m39` | M39 / 116 | GRCm39 | `data/cache/mouse_gencode_m39` | `data/builds/mouse_gencode_m39` |

Pairings come from the official [human](https://www.gencodegenes.org/human/releases.html)
and [mouse](https://www.gencodegenes.org/mouse/releases.html) histories.
Python and R share `backend/data/dataset_profiles.json`. The actual archive
registry, species-specific mart and assembly are verified, not inferred from dates.

## Prepare and select

```bash
./scripts/setup_local.sh --dataset human-gencode-v45 --no-start
./scripts/setup_local.sh --dataset human-gencode-v50 --no-start
./scripts/setup_local.sh --dataset mouse-gencode-m39 --no-start
./run_local.sh --dataset human-gencode-v50
```

Run only the setup commands you need. Each builds its selected profile and leaves
others unchanged. The toolbar lists installed, validated packages, not every
preparation preset. Restart the service after installing another dataset;
changing the selector performs no downloads. `--cache DIR` and `--query-cache DIR`
override preparation locations; use separate caches for different datasets.

SpliceImpactR's public `get_annotation()` takes GENCODE numbering (human `50`,
mouse `"M39"`). Feature mart queries take the paired **Ensembl** release (`116`
for both). These are not interchangeable numbers.

To use previously downloaded complete inputs, supply all three files:

```bash
Rscript --vanilla scripts/prepare_spliceimpactr_cache.R \
  --dataset human-gencode-v50 --output data/cache/human_gencode_v50 \
  --base-dir data/spliceimpactr-cache/human_gencode_v50 --skip-exon \
  --gtf /path/to/gencode.v50.annotation.gtf.gz \
  --transcript-fa /path/to/gencode.v50.pc_transcripts.fa.gz \
  --protein-fa /path/to/gencode.v50.pc_translations.fa.gz
PYTHON=.venv/bin/python ./scripts/build_annotations.sh \
  data/cache/human_gencode_v50 --dataset human-gencode-v50 --scope full
```

Verified existing raw files avoid repeating SpliceImpactR's analysis-oriented
processed-object creation. Cold accession calls its public `get_annotation()`
and keeps only checksum-verified, unmodified downloads. Its filtered processed
object is never the browser catalog. Large releases can need several GB of RAM;
avoid concurrent full-genome builds.

## Scientific invariants

- Every raw transcript remains catalogued: TSL 1–5, NA/unscored, noncoding,
  incomplete-CDS, feature-empty and missing-sequence models alike.
- Official raw MD5s, GTF headers, species-specific IDs, assembly bounds and
  complete inventories are checked. Independent R/Python transcript-ID hashes agree.
- Full chromosome lengths come from assembly metadata, not maximum gene
  coordinates; chromosome/mitochondrial aliases are species-aware.
- Feature queries have no TSL/biotype selector. Original amino-acid intervals
  and distinct coincident accessions survive. Only exact independently verified
  nucleotide/protein mappings generate genomic feature segments.
- Successful empty coverage and unavailable sources are distinct and carry
  explicit statuses/reasons. Remote transport/query failures block completion.
- Detached exports carry dataset, species, GENCODE/Ensembl, assembly and build
  identity. Notes/sessions/caches are dataset/build-scoped. Legacy v45 workspaces
  migrate on first save without deleting the old record.
- PPI switch predictions stay disabled. Optional human gene-level context is
  separately data-hashed and bound to the exact annotation build. No human
  interaction dataset is applied to mouse.

Whole-genome reference serving is optional. Human v45/v50 can use the existing
checksum-pinned GRCh38.p14 adapter. Mouse reference byte-range setup needs a
separately verified GRCm39 reference profile and is not yet supported; mouse
transcripts, sequences and projected protein features do not require it.

## Another release

Reuse SpliceImpactR's species/release accession, not a new downloader. Before
adding a profile, independently verify official release pairing, raw checksums
and inventories, assembly lengths, ID prefixes and the actual matching mart
registry/species dataset. Add mismatch, retention, projection, API isolation and
release-backed tests. Publish a new build, never a relabeled old database;
unavailable archives must not fall back to a latest service.

Source fixtures and live gene checkpoints are not full-install evidence. Full
preparation, SQLite validation, UI checks and deterministic rebuild receipts are
separate per-profile gates; see `testing.md` and `setup_validation.md` for evidence.
