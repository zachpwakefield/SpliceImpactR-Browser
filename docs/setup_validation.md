# Isolated local setup validation

This records the September 29, 2026 setup audit. It is test evidence, not a
claim that every operating system, browser, or biological interpretation has
been validated. Generated annotation files, databases, logs, and machine paths
are deliberately not included.

## Environment and installation

A fresh public source clone was tested with an isolated R 4.6.1 environment,
a new R package library, a project Python 3.9.6 virtual environment, and
Node 24.19.0 / pnpm 11.25.0. Released SpliceImpactR 1.0.0 was installed from
Bioconductor 3.23 using the documented installer, not a vendored package or
private development library. The actual library search path was checked.
Relevant installed versions were biomaRt 2.68.0, data.table 1.18.6.1, and
jsonlite 2.0.0.

The first source-based R installation exposed a missing CMake prerequisite
for `nloptr`. Adding CMake to the isolated environment and rerunning the
installer succeeded; the README now explains that prerequisite. Native macOS
binary installations and a full clean operating-system installation were
not tested by this audit.

The initial GitHub Ubuntu R job subsequently failed before reaching the adapter
tests: source installs of `png`, `curl`/`RCurl`, and `Rhtslib` could not find
the PNG/libcurl development headers. Their missing dependencies then prevented
SpliceImpactR from installing. CI and the Ubuntu/WSL2 setup instructions now
explicitly install the compiler/CMake and development-library prerequisites.
A corrected CI result, not the earlier local installation, is required to
confirm that Linux installation path. Push checks are limited to `main` and
pull requests are checked separately, avoiding duplicate push/PR installations
for the same review-branch update.

The Python lock was also checked against an isolated Python 3.14.7 environment:
all dependencies installed as wheels. The updated FastAPI/Pydantic/Starlette
combination passed all 26 backend/API/PDF tests on both Python 3.9.6 and 3.14.7
with warnings treated as errors, and both environments passed `pip check`.
Pillow remains version 11.3.0 on Python 3.9 and is 12.3.0 on Python 3.10+.
Source CI now independently checks Python 3.9, 3.11, and 3.14.

The documented `./scripts/setup_local.sh --no-start` command completed through
frontend build, dependency installation, feature preparation, and full SQLite
publication. Official raw inputs and archive queries were obtained during
this audit; verified upstream download/query caches were reused on retries.
No private original browser database or workstation-specific feature RDS was
required. No whole-genome reference or `samtools` was used.

## Complete annotation and feature checks

The independent raw-GTF importer and R adapter agreed on the complete
252,930-transcript inventory and 63,187 genes. All raw GTF feature rows were
processed. TSL 1–5, unscored/NA values, every biotype, and incomplete CDS models
were retained. Default UI transcript filters were empty.

All seven feature sources were prepared against the explicit Ensembl 111
archive or the public ELM endpoints and normalized through the released
SpliceImpactR public API. The full build imported 1,262,991 feature records.
These are observed preparation results, not required counts for future remote
refreshes. Raw-file identities, prepared feature digests/counts, transcript
inventory, foreign keys, and exact-only CDS projection gates passed.

PGK1's six v45 transcript models included TSL 5 PGK1-205 and unscored PGK1-206.
Both were selectable in the UI; PGK1-205 remained a model without a translated
product, and PGK1-206 retained its 389-aa protein. Newer Ensembl catalogs can
contain additional PGK1 transcripts; those do not belong to the pinned v45
source and are not synthesized by this browser.

## Automated core release gate

Two full builds with identical finalized inputs/code produced identical
manifests, validation reports, row counts, and canonical table content hashes.
The verified build hash was:

```text
f41ac5620bf9e9cf6e81192a0f2153eb780faf8e29b405023becbede8cde9a9a
```

`./scripts/verify_release.sh` passed with the actual cache configured: 43
data/builder tests, 26 backend/API/PDF tests, and 114 frontend tests (183 total,
no skipped cases), plus TypeScript checks, the production build, offline bundle
audit, verified full-database startup, and conflict-copy scan. The separate
released-package R integration and first-install-library fixtures also passed.
The publication audit passed after local data generation and dependency setup.
The SQLite database was approximately 3.33 GB; dependencies and caches are
additional disk usage.

## Browser observations

A new temporary Chrome 154 profile at 1440 × 1000 / DPR 1 exercised PGK1 and
SP1 search, lower-support model selection, protein expansion, zoom, keyboard
pan, fit-to-gene, two-transcript comparison, sequence inspection, local session
export, and a downloaded local PDF report. ANK2's 129 models were available
through the navigator while mounted transcript rows remained bounded; an
explicit scroll position was not pulled back to selection.

That exercised workflow produced no console errors/warnings, failed HTTP
responses, or external resource requests. It does not prove performance under
all cold-cache conditions or correctness under every supported engine.

A subsequent replay with the updated Python 3.14 runtime exposed a real
stale-search race: hovering a PGK1 option, replacing the query with SP1, and
immediately submitting could activate the previous option. The query now
clears the old choices, resets active selection, and exposes selectable options
only in the ready state; aborted replies cannot publish stale results. Two
additional frontend regressions passed (116 frontend tests total). A controlled
800-ms SP1 response delay reproduced the fault before the change and selected
SP1 correctly afterward with zero stale options. The complete PGK1/SP1/ANK2
Chrome workflow, including local PDF download, then passed again with no console
errors/warnings, failed HTTP responses, or external requests.

Python 3.14 also passed verified full-database startup and live API smoke tests
for both translated PGK1 models and canonical SP1. The annotation build hash
was unchanged by these runtime/interface corrections.

The final updated local core release gate then passed 43 data/builder,
26 backend/API/PDF, and 116 frontend tests (185 total, no skips), along with
TypeScript, production build, offline-bundle, full-startup, and conflict-copy
checks. The data/builder suite used Python 3.14; the project backend suite used
Python 3.9, with the separate 26-test Python 3.14 backend and live runtime replay
also passing. This does not replace the independently required Linux R CI job.

Final first-install review also added an explicit writable-library preflight.
Its offline test creates a missing personal R library, promotes an existing
writable library, and rejects an unset personal-library fallback. This avoids
a non-interactive install depending on administrator-owned system libraries.

## Remaining review boundaries

- Cross-engine Firefox/WebKit/Safari and an actual native desktop installation
  replay were not part of this new setup audit.
- Biological interpretation sign-off and unfamiliar-scientist usability tasks
  still need human reviewers.
- The optional reference-enabled build and the full optional exon audit were
  not exercised here; both-strand exon/projection fixtures were tested.
- Repository-owner license selection remains separate from successful setup.

Use [testing.md](testing.md) to reproduce source, generated-data, live API,
deterministic-build, and release checks. Keep new evidence separate from the
historical application review observations in [limitations.md](limitations.md)
and [review_log.md](review_log.md).
