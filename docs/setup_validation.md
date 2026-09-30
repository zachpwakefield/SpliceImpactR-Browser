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
A corrected CI result, not the earlier local installation, was required to
confirm that Linux installation path. Both corrected review-branch runs
[7](https://github.com/zachpwakefield/transcript-browser-shareable/actions/runs/36641014609)
and [8](https://github.com/zachpwakefield/transcript-browser-shareable/actions/runs/36642405540)
passed: fresh Linux installation of SpliceImpactR 1.0.0, complete-annotation
integration, frontend, and Python 3.9/3.11/3.14 checks. The Linux R fixture
does not replace a full Linux scientific download/build. Push checks are limited to `main` and
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
also passing. The independent corrected Linux R CI job subsequently passed.

Final first-install review also added an explicit writable-library preflight.
Its offline test creates a missing personal R library, promotes an existing
writable library, and rejects an unset personal-library fallback. This avoids
a non-interactive install depending on administrator-owned system libraries.

A subsequent isolated Firefox 153 workflow at 1440 × 1000 / DPR 2 passed the
same PGK1/SP1/ANK2 selection, expansion, zoom/pan, comparison, sequence, session,
and local PDF checks with no console errors/warnings, failed HTTP responses,
or external resources. The Playwright WebKit 26.5 test engine crashed before
creating a page on this machine; it supplies no WebKit/Safari acceptance
evidence and was not classified as an application failure.

## Optional Mac launcher replay

The public source review found two missing packaging helpers, a fixed old
annotation hash, and a required project-folder name that did not match a normal
GitHub clone. The restored local packager records each installed build,
frontend identity, and Python interpreter. The materializer validates private
data clones without changing source metadata; the native launcher discovers
the installed runtime rather than a Desktop project name.

On Apple Silicon macOS 26.0.1 with Swift 5.8.1, the public build/install scripts
compiled and ad-hoc-signed the application, installed it in an isolated temporary
home, and prepared the full immutable database using an APFS clone. Reinstall
verified/reused the existing runtime. A no-window/no-browser native self-test
started the packaged Python 3.9 service, confirmed full-build and frontend
identity, selected another loopback port because the default port belonged to
a different build, and stopped its own server cleanly. The pre-existing local
services remained available afterward. The real installed application, Dock,
Desktop, and Application Support were not modified.

A separate server using that installed private backend/site-packages/frontend
and full data clone also passed the complete Firefox 153 / DPR 2 workflow,
including protein sequences, comparison, local session download, and PDF
generation. No console warnings/errors, failed HTTP responses, or external
resources were observed. This checks installed runtime functionality separately
from native readiness.

Nine cross-platform packaging tests passed on Python 3.9 and 3.14 with warnings
treated as errors (35 backend tests total). They check bundle contents,
runtime/scientific identity separation, unchanged originals, independent
clones, code/data tampering, non-overwrite, safe relative paths, and reference
relocation with exact final-path identity receipts and a tiny range response.
The publication audit now also rejects forcibly staged app bundles or generated
runtime ZIPs/manifests, including outside the default ignored output directory.
This is not a full-genome optional-reference installation or a visual Dock/Finder
interaction test. Native source compilation/signing is also required in CI.

After the launcher and publication changes, the final core release gate passed
44 data/builder, 35 backend/packaging/API/PDF, and 116 frontend tests (195 total,
no skips), plus deterministic-rebuild, TypeScript, production build, offline
audit, full-database startup, and conflict-copy checks. Both Python 3.9 and
3.14 independently passed the 35 backend tests with warnings treated as errors.
The scientific annotation build identity remained unchanged.

## Owner-selected license and final local check

The repository owner selected MIT for the original browser source. The root
license, README, and frontend package metadata now agree; SpliceImpactR's GPL-3
license and annotation-data terms remain separate. License/notice files are
also included in the locally generated Mac bundle and its private runtime.

After these changes, the automated core gate passed 45 data/builder, 35
backend/packaging/API/PDF, and 116 frontend tests (196 total, no skips). The
full-database startup and deterministic-build identity remained unchanged.
The isolated native installer, resource/signature checks, and self-test passed;
the self-test started and stopped only its own server.

A first attempt in a restricted command runner aborted inside macOS application
registration, before launcher startup. The same signed bundle passed with
access to the macOS GUI services. This environment restriction is separate
from scientific-package or launcher validation; native self-tests need a
logged-in GUI session even when they display no window.

## Application 1.2 dataset/default-track audit — September 30, 2026

The source now shares three closed Python/R release profiles: human
v45/Ensembl 111/GRCh38.p14, human v50/Ensembl 116/GRCh38.p14, and mouse
M39/Ensembl 116/GRCm39. All nine official raw-file MD5 declarations and all
primary chromosome lengths were independently reconciled against upstream
metadata. A human chr18 length typo was caught by real-package startup,
corrected, and covered by a metadata regression; the gate was not weakened.

Actual full raw GTF/FASTA inventories and species/version/gene/peptide
identities were checked for all profiles. The raw v50 GTF contains 644,292
transcripts and 78,733 genes, including **44 PGK1 models** (40 translations).
Mouse M39 contains 481,871 transcripts and 78,289 genes; Sp1 has ten models
and ten translations. These are raw-input observations, not evidence of a
completed new feature preparation or SQLite installation. The old full v45
data remained unchanged at build `37ca61173524f4267052168e2db7a5c3bc9442ca625eb5e09afb8e96451e1d33`
with its optional verified human reference.

The final source gate passed **67 data/tooling, 44 backend/API/PDF/native,
and 133 frontend tests (244 total, no skips)**, plus TypeScript, production
build, privacy audit, R parsing and complete offline R adapter/profile tests.
The R accession tests use mocked public calls; they do not prove a real cold
download. Newer pnpm's automatic pre-script installation is explicitly disabled
in test gates so they do not unexpectedly download or replace dependencies.

Two independent methodology/code review passes covered release binding,
original feature bounds/accessions, dataset isolation, exports, native
packaging, and All/Top/None defaults. Top self-comparison/stale-feature state
and a pending-default restore race were found and fixed. Idle feature rows
now report loading rather than successful empty coverage.

Chrome 154 and Firefox 153 both passed the three-dataset tab/selector,
same-ID sequence-isolation, unavailable-source, note-switch guard, workspace
and export checks. Those used deliberately tiny **synthetic** human/mouse
contracts, not full new scientific builds. Against the actual complete v45
package, both engines passed All/Top/None, TPM1-229, individual collapse/reopen,
ANK2 translated rows beyond 25 with bounded DOM/initial feature demand, and
explicit session/history restoration during deterministically delayed gene
loads. No external runtime requests or browser errors were observed.
All mode uses viewport/context-based demand, not a strict global request-count
cap: existing per-batch workers may overlap while rapidly scrolling.

The final application-1.2.0/build-6 Mac bundle compiled and passed ad-hoc
signature verification. In an isolated test state directory, it materialized
and fully verified private clones of the existing v45 SQLite package and its
optional human reference FASTA/FAI, then passed no-window launcher readiness
and owned-server shutdown. The user's installed application and its active
server were not replaced or stopped. Multi-dataset packaging beyond the actual
v45 package is supported by contract fixtures, not full new scientific data.

The one-isoform domain concern was independently checked against the installed
API and immutable database: SP1 had calls for 4/4 transcripts (domain calls on
two), TPM1 for 19/39, and FGFR3 for 6/10. TPM1-229 had 7 InterPro, 1 Pfam and
2 MobiDB-lite calls. Selecting a collapsed row had not expanded its lanes;
there was no one-transcript import cap. All/Top/None now makes that starting
behavior selectable without inventing annotations for uncovered products.

### Explicitly open scientific gates

Full v50/M39 feature preparation, SQLite/projection validation, two-build
determinism and full biological UI acceptance have **not** completed. Final
single-gene release-116 checkpoints failed because the pinned archive
intermittently timed out or returned HTTP 200 HTML titled “Service unavailable”.
Fresh R and independent curl reproduced the outage before any protein FASTA
was loaded; the release-111 registry returned valid XML immediately afterward.
The browser now gives an actionable outage error and never falls back to a
different release. An earlier partial mouse result that ended unsuccessfully
was not counted as a passed checkpoint. No GitHub publication or replacement
of the user's existing installed app occurred during this refactor.

PPI switch predictions remain disabled pending a corrected, validated upstream implementation.
Optional mouse whole-genome reference serving remains unsupported. Actual
Safari, unfamiliar-user and domain-scientist sign-off are still separate gates.

## Feature-call comparison and human PPI-context audit — September 30, 2026

Compare now displays actual source/accession/method calls and original AA
ranges for each isoform. Repeated calls remain independent; a coordinate shift
is not a biological gain/loss claim. Valid-empty, unavailable, loading/error,
missing-product, unidentified accession and invalid-bound observations remain
distinct. Full CSV/TSV exports include explicit provenance and complete call
arrays, independent of visible page/search or Canvas-source filters. Selecting
a comparison-side call preserves the comparison pair.

The optional human context was exported through the public released
SpliceImpactR 1.0.0 `get_ppi_interactions()` API: **773,471 records and 16,077
genes**, with independent input/resource hashes and inventory checks. It was
imported into a separate immutable sidecar, leaving the full v45 annotation
build unchanged. Its context hash is
`f81b0ede43c2673beab5ea20ef6ce3ee042fc20aa9fe53627978a26d5c07d641`.
Real read-only endpoint checks found 97 feature-linked/330 total records for
SP1, 28/233 for TPM1 and 55/284 for FGFR3. These are resource records, not
isoform interaction predictions or probabilities. The network date and
Ensembl-release correspondence are explicitly unknown; mouse receives no
human context. Aggregated endpoint lists are preserved, not reconstructed as
paired mechanisms.

Independent methodology/code review and a public-API synthetic reproduction
confirmed the endpoint-attribution blocker in `get_ppi_switches()`: changing a
token recorded on the partner side can be counted against the focal gene even
when that edge's recorded focal requirement is unchanged. This does not imply
misassigned GTF models or transcript-domain records. Switch predictions remain
disabled; no upstream package was patched or vendored.

The source gate passed **75 data/importer/tooling, 54 backend/API/native and
160 frontend tests (289 total, no skips)**, plus complete offline R contracts,
R parsing, privacy checks, TypeScript and production build. The final section
shortcut markup was additionally checked by rerunning all 160 frontend tests,
TypeScript and the production build. Chrome and Firefox then both passed the
actual full-v45 comparison/context workflow against those rebuilt assets:
individual calls, shared/different observations, accession search, complete
TSV export, filter independence, endpoint-owned paged context, and inspection
of either member without losing the pair. Neither browser reported errors or
external runtime requests. Updated README screenshots were captured from this
real-data workflow and visually reviewed.

The isolated Apple Silicon Mac bundle compiled and passed signature checks.
Runtime `efa948dc11c72f47` fully verified private clones of the annotation,
optional human reference and new PPI sidecar, then passed launcher readiness
and owned-server shutdown. No installed application, active user server,
GitHub branch or remote repository was replaced or updated.

These checks do not close the full v50/M39 scientific-build gates or validate
isoform PPI-switch predictions, actual Safari/Intel use, or biological and
unfamiliar-user sign-off.

## SpliceImpactR Browser naming audit — September 30, 2026

The user-facing application is now **SpliceImpactR Browser**: toolbar/startup
mark, annotation-aware browser title, About/diagnostics, session filename,
CLI/API descriptions, PDF header/author, native window/menu/accessibility
labels, app bundle/executable and installer/CI instructions. All README images
were recaptured from the real full-v45 workspace with the new name.

The source gate passed **75 data/tooling, 56 backend/API/native and 164 frontend
tests (295 total, no skips)**, plus R contracts, parsing, TypeScript and the
production build. New regressions check rendered identity, initial and
annotation-aware document titles, native property-list/script agreement, API
fallback branding, PDF text/metadata and unchanged session/storage identities.
Chrome and Firefox passed the live UI/title/About/session checks alongside the
feature-comparison and context workflows, with no browser errors or external
runtime requests.

An isolated temporary-home installation built, signed and installed
`SpliceImpactR Browser.app`, created its newly named Desktop link and passed
the new executable's launcher readiness/owned-server shutdown self-test.
Stable session/schema/storage keys, HTTP headers, native bundle identifier
and legacy runtime/log paths were deliberately retained; the annotation build
was not changed. The actual installed app, Dock and GitHub repository were
not modified by this audit.

## Owner-requested installed launcher and Dock pin — September 30, 2026

After the isolated naming audit, the owner requested a regular Dock launcher.
The renamed bundle was installed alongside the preserved old bundle, with
validated private annotation/reference/context data, a new Desktop link and
verified ad-hoc signature. Installed runtime `c6f8d78f08bbfd97` passed its
no-window readiness and owned-server shutdown self-test.

The Dock preferences were backed up locally before adding one persistent app
entry. All 41 prior pinned entries retained their order/content; read-back
after a Dock refresh showed 42 entries including the newly named app. This
was an explicitly authorized local preference operation, not a default
behavior added to the repository installer. The old launcher was gracefully
quit, the new launcher opened, and an unrelated development server was left
running.

Chrome's disposable-profile acceptance test against the actual installed
runtime passed identity/title/About/session compatibility, feature-call
comparison and exact endpoint-owned PPI-context checks, with no browser errors
or external runtime requests. No scientific annotation build was changed.
Physical Dock-icon/Finder interaction and biological sign-off remain separate
human checks. GitHub branch heads were read-only checked and remained at the
prior MIT-license commit; no source changes were committed or pushed here.

## Remaining review boundaries

- Actual desktop Safari, a working WebKit engine, Intel native installation,
  and physical Dock/Finder interaction remain unverified by this setup audit.
- Biological interpretation sign-off and unfamiliar-scientist usability tasks
  still need human reviewers.
- The September 29 preparation did not construct a reference-enabled build;
  September 30 verified the existing optional human reference and its private
  native clones. New-profile reference setup and the full optional exon audit
  remain separate; both-strand exon/projection fixtures were tested.

Use [testing.md](testing.md) to reproduce source, generated-data, live API,
deterministic-build, and release checks. Keep new evidence separate from the
historical application review observations in [limitations.md](limitations.md)
and [review_log.md](review_log.md).
