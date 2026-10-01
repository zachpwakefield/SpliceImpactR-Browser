# Scope and limitations

## Data

The main datasets are human GENCODE v45 and mouse M34, both paired with
Ensembl 111. They retain every source GTF transcript, including low-support,
unscored and noncoding models. Counts can differ from a newer Ensembl website.
Experimental v50/M39 profiles are in the registry but have not passed a full
download/build installation.

Feature coverage varies by isoform and source. Missing calls do not remove a
transcript. Source calls remain independent; confidence scores, e-values and
per-database release labels are not supplied. The preparation inputs do not
provide every noncoding transcript sequence.

## Visualization and interpretation

Detailed transcript rows show one selected gene at a time; the genomic overview
can show neighboring genes. Alignment, variant, expression and other general
genome-browser tracks are not implemented.

Genomic protein projections and event-to-residue highlights require an exact
coding map. Intronic and UTR intervals have no protein projection. Highlights
mark touched residues, not predicted sequence or splice changes. Comparison
shows differing feature calls and ranges, not a residue alignment or a domain
gain/loss prediction.

Optional PPI context shows recorded human gene partners and feature
observations, not interaction-switch predictions; mouse PPI is unavailable.
The upstream switch method's partner-domain attribution issue remains outside
the browser's supported workflow.

## Saving and platform support

Favorites, notes and views are local to a browser profile, origin and annotation
build. They do not synchronize; export a session before clearing browser data.
Event highlights are limited to 100 intervals of up to 25 Mb each.

PDFs are structured reports, not Canvas screenshots. Reports are bounded to
20 transcripts, 2,000 feature rows and 20,000 sequence characters; they exclude
private notes and event highlights. Use table exports for machine-readable data.
Whole-genome reference sequence is an optional human capability, not required
for transcript browsing.

Full v45/M34 and Chrome/Firefox workflows have been tested, along with an
Apple Silicon Mac launcher. Safari, Intel Mac installation and a complete
Linux/WSL scientific installation remain unvalidated. Detailed results are in
[validation history](setup_validation.md).
