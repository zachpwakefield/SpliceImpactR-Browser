# Testing

For a quick installation check, start the browser and run the API smoke test.
For a code change, run the source suite and exercise the affected controls.
The commands below run from the repository root unless stated otherwise.

## Check an installation

Start the prepared human dataset:

```bash
./run_local.sh --no-open
```

In another terminal:

```bash
python3 scripts/smoke_test_api.py \
  --base-url http://127.0.0.1:8000 \
  --dataset human-gencode-v45 --gene-query SP1 --expect-scope full
```

Use the URL printed by the server if its port differs. For mouse, replace the
dataset with `mouse-gencode-m34` and the gene with `Sp1`. The script checks the
dataset identity, health, search, genomic region, transcript, features and
protein sequence.

Then try this short browser checklist:

1. Search for a gene and a transcript; confirm the selected annotation release.
2. Pan, zoom and fit the locus. Expand a protein track, then try **All**, **Top**
   and **None** in **View**.
3. Select a second isoform and inspect **Compare**, a feature and a sequence.
4. Add several **Event highlights**, including a coding interval and an intron;
   verify the protein projection appears only where applicable.
5. Export a table, a session and a PDF. Reload the session and check the pair,
   view and highlights.
6. Repeat at narrow and wide window sizes. Check the browser console for errors
   and the Network panel for requests outside the local server.

For a problem report, include the app version, dataset/build hash, gene or
transcript, action and screenshot. **About & diagnostics** provides a shareable
receipt. Omit private notes and local file paths.

## Check a code change

```bash
./scripts/test_source.sh --require-all
```

This runs the publication audit, Python and R checks, builder/data contracts,
backend tests, frontend tests, TypeScript and the production build. Use the
prepared project environment and ensure `pnpm` is on `PATH` (setup can use a
temporary `npx` copy). `./scripts/test_source.sh` runs what is
available and reports missing dependencies as `SKIP`; review those lines.

The suite covers both strands, split codons, noncoding/incomplete models,
source availability, dataset isolation, comparisons, event projections,
persistence, exports and packaging. Generated full-build tests run when their
data packages exist. GitHub Actions runs source checks on clean runners; it
does not download and build the whole scientific catalog.

### Small build fixture

With a prepared human v45 cache, build the four-transcript SP1 fixture:

```bash
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache --scope sp1
./run_local.sh --dev-fixture --no-open
```

The generated fixture lives in `data/builds/sp1_fixture/`. The source suite
checks its sequences, counts, database integrity and exact coding projections.
This is a fast builder checkpoint, not a complete annotation installation.

## Automated browser checks

Install Playwright in your test environment; it is not needed to use the app.
Build the frontend and keep a server running against the appropriate full
dataset. For human v45:

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 node tests/ui/protein_defaults.cjs
BROWSER_ORIGIN=http://127.0.0.1:8000 node tests/ui/event_highlights.cjs
```

For mouse M34:

```bash
BROWSER_ORIGIN=http://127.0.0.1:8000 node tests/ui/mouse_m34.cjs
BROWSER_ORIGIN=http://127.0.0.1:8000 EVENT_DATASET=mouse-gencode-m34 \
  node tests/ui/event_highlights.cjs
```

Repeat with `BROWSER_ENGINE=firefox`. If Playwright is installed elsewhere, set
`PLAYWRIGHT_MODULE=/path/to/node_modules/playwright`; `CHROME_EXECUTABLE` can
select a local Chrome. These tests use disposable browser profiles.

After preparing [optional human PPI context](data_preparation.md#optional-human-ppi-context),
run `node tests/ui/feature_comparison.cjs` with the same origin. To test only the
dataset selector without scientific downloads, run
`.venv/bin/python tests/ui/serve_dataset_fixtures.py --port 8771`, then
`BROWSER_ORIGIN=http://127.0.0.1:8771 node tests/ui/datasets.cjs` in another
terminal. Stop test servers with Ctrl+C.

## Full-build and release checks

Preserve the first build's receipts, rebuild with identical inputs/code, then
compare. This human v45 example writes only ignored local outputs:

```bash
mkdir -p output/first-build-receipts
cp data/builds/gencode_v45/{manifest.json,validation_report.json,build_metrics.json} output/first-build-receipts/
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache --scope full
.venv/bin/python scripts/verify_deterministic_build.py \
  output/first-build-receipts data/builds/gencode_v45 \
  --output data/builds/gencode_v45/determinism_receipt.json
./scripts/verify_release.sh
```

`verify_release.sh` is the human v45 gate. For M34, use its cache/build directory
in the two-build comparison and run its full-build acceptance and scoped API/UI
checks; a human receipt is not interchangeable with a mouse receipt.

Native launcher checks are in the [Mac guide](../desktop_app/README.md).
[Release checklist](release_checklist.md), [critical review](critical_review_addendum.md)
and [validation history](setup_validation.md) hold the detailed engineering and
human-review evidence. A failed checksum, count or projection check should be
fixed at its source, not bypassed by editing a manifest.
