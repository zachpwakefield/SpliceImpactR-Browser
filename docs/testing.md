# Testing the local browser

The source distribution intentionally does not contain a database, FASTA, or
frontend `node_modules` tree. Test it in layers so a source failure is not
confused with a missing local data package:

| Layer | What it proves | Needs generated data? |
| --- | --- | --- |
| Source/privacy | No workstation paths or generated artifacts leaked; Python/R source parses | No |
| Unit/contract | Builder, API, PDF, coordinate, and frontend behavior | No |
| SP1 acceptance build | GTF/FASTA/RDS inputs produce the expected four-transcript fixture | Yes |
| API smoke | Search, region, gene, transcript, protein features, and sequence work together | Yes |
| Browser acceptance | Pan/zoom, labels, expansion, filters, comparison, exports, and keyboard behavior | Yes |
| Full release gate | Full-build counts, checksums, deterministic rebuild, offline bundle, and startup | Yes |
| Optional Mac launcher | Private packaging/data clones, build/frontend readiness, owned-process shutdown | Yes |

## 1. Run the source checks

From the repository root:

```bash
./scripts/test_source.sh
```

This runs the publication audit, syntax compilation into a temporary directory,
data-contract tests, backend tests when `.venv` has the locked dependencies, and
the R parser checks when R is installed. Frontend tests are run automatically
when `frontend/node_modules` is present; otherwise the script reports a skip.
To make a missing frontend install an error (for CI or a release candidate):

```bash
./scripts/test_source.sh --require-all
```

Install the frontend separately in a networked environment when needed:

```bash
cd frontend
pnpm install --frozen-lockfile
cd ..
```

`--require-all` requires the backend, frontend, and released R dependencies,
and runs `tests/r/test_browser_annotation.R`. The latter independently checks
all TSLs, unscored values, other biotypes, incomplete CDS, PAR_Y IDs, both-strand
split codons, and the released package's public manual-feature/exon APIs using
synthetic data. It also exercises all reviewed dataset profiles, release/species/
assembly mismatches, original feature bounds, distinct coincident accessions,
valid-empty versus unavailable sources, cache reuse and mocked public accession.
It does not download a scientific fixture. `--require-frontend`
remains available when only that dependency must be mandatory.

The GitHub Actions workflow repeats source tests, packaging-helper fixtures,
and an R adapter integration test on clean runners. It also compiles/ad-hoc
signs the native Mac launcher. CI does not download the full scientific catalog
or claim a native generated-data installation.

## Dataset-specific checks

Use `--dataset` throughout preparation/build/runtime. Reviewed IDs,
raw inputs and cache directories are in [genome_datasets.md](genome_datasets.md).
Source tests prove contracts, not full v50/M39 installation.

For an optional real release-backed **single-gene** feature-query checkpoint:

```bash
Rscript --vanilla tests/r/test_dataset_release_smoke.R \
  --dataset mouse-gencode-m34 --gene Sp1 \
  --gtf /path/to/gencode.vM34.annotation.gtf.gz \
  --protein-fa /path/to/gencode.vM34.pc_translations.fa.gz \
  --output /path/to/gene-checkpoint.json
```

The human equivalent uses `--dataset human-gencode-v45 --gene SP1` and v45
files. This verifies official raw bytes, retained gene models/translation IDs,
the pinned mart identity and returned amino-acid bounds. It does **not** build
SQLite, prove genomic projection, exercise a full cold SpliceImpactR accession,
or establish genome-wide completeness/determinism. A failed archive response
is a failed checkpoint even when raw-file validation passed.

The existing `verify_release.sh` is the historical **v45** gate. For another
profile, separately preserve/rebuild/compare that profile's receipts, verify
its full database and run the scoped API/UI checks; do not use a v45 receipt as
evidence for a different dataset.

## 2. Build the small SP1 acceptance fixture

Use a local, audited GENCODE v45/Ensembl 111 cache. A whole-genome reference is
optional and is only needed to exercise the reference-range endpoint; keep all
generated inputs outside Git (the paths below are placeholders):

```bash
PYTHON=.venv/bin/python ./scripts/build_annotations.sh /path/to/annotation-cache \
  --scope sp1
```

To include the optional reference capability, add
`--reference-fasta /path/to/Homo_sapiens.GRCh38.dna.toplevel.fa`.

The builder filters the authoritative GTF to the `SP1` locus and writes the
ignored package at `data/builds/sp1_fixture/`. It then runs the acceptance
checks in `tests/data/test_sp1_build.py`, which require:

- exactly `SP1-201`, `SP1-202`, `SP1-203`, and `SP1-204`;
- protein lengths 785, 778, 230, and 162 amino acids, respectively;
- feature-source totals matching the actual prepared/exported source receipts;
- an exact 230-aa protein sequence for `SP1-203`, regardless of feature coverage;
  and
- exact-only genomic projections with foreign-key/database integrity checks.

Do not require `SP1-203` to have zero features merely because an older
TSL-filtered cache omitted it. Empty-feature behavior is tested with a separate
synthetic fixture. A full build additionally requires the complete raw-GTF
inventory and PGK1's six v45 models, including its TSL 5 and unscored models.

If the cache has not been prepared yet, run
`scripts/prepare_spliceimpactr_cache.R` as described in
[`data_preparation.md`](data_preparation.md), or supply the three raw GENCODE
paths explicitly. Do not copy the resulting cache into the repository.

## 3. Run the API smoke test

Build the frontend once if a browser UI is desired, then start the explicitly
labeled fixture server:

```bash
cd frontend
pnpm run build
cd ..
./run_local.sh --dev-fixture --no-open
```

In a second terminal, run:

```bash
python3 scripts/smoke_test_api.py
```

The smoke test checks the health/read-only flag and manifest, resolves `SP1`
through search, verifies the gene and region endpoints, opens the default
feature-rich `ENST00000327443` transcript, requests InterPro/Pfam/MobiDB-lite/
ELM features, and verifies that a non-empty protein sequence is returned. A
different data package can be tested with, for example:

```bash
python3 scripts/smoke_test_api.py \
  --base-url http://127.0.0.1:8010 \
  --dataset mouse-gencode-m34 \
  --gene-query Sp1 \
  --expect-scope full
```

The server must remain bound to `127.0.0.1`; the smoke script should fail
clearly if it is pointed at a remote/non-running service.

## 4. Manually verify the browser behavior

Open `http://127.0.0.1:8000` after building `frontend/dist`. If using the Vite
development server instead, keep the API running and use:

```bash
cd frontend
pnpm dev
```

Then check the following on the SP1 fixture:

1. Search `SP1`, choose the gene result, and confirm the locus and four
   transcripts appear.
2. Zoom in and out, drag-pan, use the ruler/fit controls, and verify that the
   coordinate readout remains 0-based internally and 1-based for display.
3. Expand `SP1-201`; choose **Protein features**; toggle source databases and
   prediction filters; hover a feature and confirm genomic/protein
   cross-highlighting.
4. Open `SP1-203` and confirm its 230-aa sequence is available. Inspect its
   actual feature coverage; test a feature-empty transcript separately and
   confirm an explicit empty state rather than an error.
5. Pin and compare transcripts, reorder/keyboard-navigate rows, and reload a
   deep link. Verify that stale build state is rejected rather than silently
   applied.
6. Export a bounded JSON/TSV/CSV record and a PDF report; inspect that the
   identifiers, intervals, feature counts and dataset/build provenance match
   the selected rows. An empty API TSV export contains one
   `# transcript-browser-provenance` comment, not a fabricated feature row.
7. Use browser developer tools' Network panel and confirm that the production
   bundle makes no request to a CDN, analytics service, or non-loopback API.
   Repeat the core flow at a narrow and wide viewport and in at least two
   browser engines before treating the UI as release-ready.
8. Hover a gene result, replace the query with a different complete gene symbol,
   and immediately press Enter (also try a slowed API response in developer
   tools). The old query's options must disappear while loading, and the new
   exact gene must open. An old hovered/keyboard-selected option must not win.

Record failures with the build hash, request URL, selected transcript/source,
viewport, browser/version, and a screenshot. Do not attach local cache paths or
private diagnostics to a public issue.

### Optional automated browser regressions

Playwright is an external test dependency, not a browser runtime dependency.
The four-dataset selector/isolation test runs against deliberately tiny
synthetic contracts, created outside the repository:

```bash
.venv/bin/python tests/ui/serve_dataset_fixtures.py --port 8771
# In another terminal with Playwright available:
BROWSER_ORIGIN=http://127.0.0.1:8771 node tests/ui/datasets.cjs
```

Set `PLAYWRIGHT_MODULE` to an installed Playwright module path when it is not
resolvable from the checkout. `BROWSER_ENGINE=firefox` selects Firefox;
`CHROME_EXECUTABLE` optionally selects a local Chrome binary. Stop the fixture
server with Ctrl+C. Its padded metadata and artificial human/mouse records are
API fixtures, never biological evidence or data to distribute.

Against a running **complete v45** package, test All/Top/None, individual
collapse persistence, TPM1-229, dense ANK2 lazy demand, and delayed explicit
session/history restoration:

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 node tests/ui/protein_defaults.cjs
```

This test must not run against the tiny selector fixture or an unrelated
release. Run both browser engines and keep installation/projection/determinism
claims separate from these observed interaction checks.

Against a running **complete mouse M34** package:

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 node tests/ui/mouse_m34.cjs
BROWSER_ORIGIN=http://127.0.0.1:8000 BROWSER_ENGINE=firefox node tests/ui/mouse_m34.cjs
```

This checks the actual release-111 identity, complete Sp1/Tpm1/Fgfr3 isoform
counts, All protein tracks, individual feature-call comparison, mouse PPI
exclusion and loopback-only runtime requests. It requires the production
frontend and M34 data, not the synthetic selector fixture.

`tests/data/test_mouse_build.py` runs automatically with the source suite when
`data/builds/mouse_gencode_m34` exists. Its full-build checks cover independent
raw transcript-ID/TSL inventories, release-pinned feature receipts, exact-only
projection, SQLite integrity and canonical content hashes. Preserve first-build
receipts and use `scripts/verify_deterministic_build.py` after a second M34 build
as described below; the historical v45 release script is not the M34 gate.

## 5. Full-build and release checks

After a complete `gencode_v45` package and deterministic rebuild receipt have
been produced, run:

```bash
./scripts/verify_release.sh
```

To produce the two-build receipt, preserve the first build's three small
receipts, rebuild with identical inputs/code, and compare:

```bash
mkdir -p output/first-build-receipts
cp data/builds/gencode_v45/{manifest.json,validation_report.json,build_metrics.json} output/first-build-receipts/
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache --scope full
.venv/bin/python scripts/verify_deterministic_build.py \
  output/first-build-receipts data/builds/gencode_v45 \
  --output data/builds/gencode_v45/determinism_receipt.json
```

The publication audit checks publishable Git files, not ignored local caches.
It must still pass after a full setup, and must fail if generated data is
accidentally tracked/staged. It is a conservative pattern audit, not a proof
that arbitrary private information can never be present; review staged files.

That gate checks the full manifest, two-build determinism, all Python/backend
and frontend tests, the offline bundle audit, full database startup, and
FileProvider-conflict filenames. If an optional reference is present, run
`./run_local.sh --full-reference-verify` separately to exercise its slow
checksum path. The separate human gates—fresh-machine
replay, cross-browser interaction review, performance review, and biological
interpretation review—are listed in [`release_checklist.md`](release_checklist.md).

## Interpreting failures

- A publication-audit failure is a privacy/release blocker.
- A missing dependency is an environment/setup issue; install from the lock
  files and rerun rather than weakening the test.
- A builder count/checksum/translation failure is a data-contract failure; do
  not edit the manifest by hand.
- A 404 from an endpoint usually means the requested stable ID is not in the
  selected scope. Repeat with the ID returned by `/api/v1/search`.
- An empty feature response can be biologically valid (for example a transcript
  with no available calls in the selected sources);
  distinguish it from an HTTP or build-validation error.

## Optional native Mac checks

See [the desktop launcher guide](../desktop_app/README.md#update-or-diagnose)
for installation, no-window/no-browser `--self-test`, and a temporary-home
replay. The cross-platform backend suite tests archive contents, runtime versus
scientific identity, private independent clones, unchanged source files,
corrupt code/data rejection, non-overwrite, traversal/symlink boundaries, and
optional-reference relocation/receipts using a tiny synthetic reference.
It does not replace full-genome reference or physical Dock/Finder checks.

## Feature-call comparison and optional human PPI context

The source gate includes exact source/accession/method comparison, repeated
calls, loading/error/unavailable states, original out-of-bounds calls, complete
CSV/TSV provenance, spreadsheet safety, and comparison-side feature ownership.
It also checks the public R context exporter, streaming sidecar import,
endpoint A/B/self ownership, per-dataset binding, rejected/corrupt/absent context,
mouse exclusion, and private native sidecar cloning. A shared synthetic API
fixture is validated by both the backend and frontend suites.

For an actual human v45 build, first prepare the optional context following
[the README](../README.md#optional-human-ppi-context), restart the server, and
run the real-browser acceptance script. Install Playwright separately in a
test environment; it is not an application dependency. Supply the module path
if that environment is outside the checkout:

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 \
  BROWSER_ENGINE=chromium \
  PLAYWRIGHT_MODULE=/path/to/node_modules/playwright \
  node tests/ui/feature_comparison.cjs
```

Repeat with `BROWSER_ENGINE=firefox` and its installed Playwright browser.
`CHROME_EXECUTABLE` optionally selects a local Chrome executable. The script
uses a disposable browser profile and checks actual SP1 feature calls,
inspection of either isoform without losing the pair, full TSV download,
Canvas-filter independence, context paging/filtering, provenance, product
titles/About/diagnostics and compatible session exports, no browser errors
and no external runtime requests. It expects the reviewed v45 package,
not a tiny fixture or another release. Optional `BROWSER_SCREENSHOT` and
`PPI_SCREENSHOT` paths capture the two Compare sections after testing.
`EXPANDED_SCREENSHOT` and `SEQUENCE_SCREENSHOT` capture their corresponding
initial transcript/sequence views; all captures use a disposable profile.

This is evidence for recorded feature differences and gene-level interaction
context, **not** validated PPI switch predictions or full v50/M39 builds. The
public `get_ppi_switches()` endpoint-attribution issue remains a separate
scientific blocker. On macOS, headless browser/native tests still need access
to GUI services; an engine abort before page creation is not an app assertion.

## Genomic event highlights

The source suite tests list parsing, assembly bounds, exact-only projection,
RNA order, intron/UTR/noncoding/unavailable states, terminal-stop exclusion,
codon completeness across exon junctions, and build-scoped state restoration.
An independent per-base oracle covers 30,012 small intervals with phase-one
and phase-two split codons on both strands.

Against a prepared full build and running server, use a disposable Playwright
profile (Playwright is a test dependency, not an app dependency):

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 \
  BROWSER_ENGINE=chromium \
  PLAYWRIGHT_MODULE=/path/to/node_modules/playwright \
  node tests/ui/event_highlights.cjs
```

Repeat with `BROWSER_ENGINE=firefox`, and with
`EVENT_DATASET=mouse-gencode-m34` when that full build is installed. Optional
`CHROME_EXECUTABLE` selects a local Chrome. `EVENT_DPR=2` tests retina rendering;
`EVENT_SCREENSHOT` and `EVENT_NARROW_SCREENSHOT` capture wide/narrow layouts.
The script checks SP1/TPM1/FGFR3 plus reverse-strand TP53 for human, or
Sp1/Tpm1/Fgfr3 plus reverse-strand Brca1 for mouse. Expected protein coordinates
are calculated directly from API coding bases, independently of the frontend
projection helper. Checks include comparison isoforms, intron/UTR exclusions,
non-disruptive adding, fit/pan/zoom, invalid-input atomicity, sessions,
Back/Forward, reload, other-chromosome context, dataset isolation, and absence
of browser errors/external runtime requests.

These tests assess coordinate highlighting, not predictions of splice,
sequence, domain, or interaction changes. Scientific PDF reports intentionally
do not contain user highlight context.
