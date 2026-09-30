# Current limitations and claim boundary

The checked normal package materializes the full primary-contig GENCODE v45 annotation and all seven locally supplied protein-feature sources. The separate SP1 package remains an explicitly labeled acceptance fixture; normal startup cannot silently fall back to it.

The main installation profiles are human v45/Ensembl111/GRCh38.p14 and mouse
M34/Ensembl111/GRCm39. The full M34 preparation, repeated deterministic build,
API/browser checks and isolated Mac installation passed on September 30, 2026;
see [setup_validation.md](setup_validation.md) for evidence and review boundaries.
The registry also retains experimental human v50/Ensembl116 and mouse
M39/Ensembl116 profiles. Their source/API fixtures and gene checkpoints are not
full genome-wide setup acceptance. These are separate scientific builds, not
additional models inserted into v45 or M34. Four reviewed profiles are
selectable for preparation; adding another release requires verified metadata
and tests. Optional mouse whole-genome
reference serving and PPI prediction display are not implemented. Optional
human gene-level PPI context and focal feature observations are supported
separately; they do not enable interaction-switch predictions.

The latest isolated public-source installation, complete-model inventory,
corrected Linux CI, cross-engine observations, and private Mac packaging
evidence are recorded in [setup_validation.md](setup_validation.md). The dated
application-1.1.x observations below remain historical evidence, not proof that
every platform or human-review gate passed in the current setup audit.

The release makes only the claims supported by the local inputs:

- Each catalog is the selected profile's unmodified GENCODE annotation, not
  whatever release the current Ensembl website displays. Every source model is retained, including TSL 4/5, unscored and
  incomplete-CDS models. The explicit BioMart adapter has no TSL/biotype query
  selector, but source availability and sequence confirmation still limit
  feature coverage for individual isoforms. Original intervals and accessions
  are preserved across SpliceImpactR normalization. Model
  completeness does not guarantee protein-feature coverage. Catalog upgrades require a
  coordinated scientific release-contract change.
- Search indexes GTF names and stable identifiers, not a complete HGNC synonym catalog, and is not typo tolerant.
- A unique exact gene-symbol submission navigates directly to that gene even when transcript or prefix suggestions are present. This is a navigation rule, not synonym inference: distinct gene records with the same exact symbol remain ambiguous and require stable-ID/locus selection.
- Noncoding transcript sequences are absent from the supplied FASTA set.
- Protein features have local source, accession, method, interval, and audit provenance, but no confidence scores, e-values, or per-database release labels. Preparation records the Ensembl archive release and ELM download digests separately.
- Overlapping calls remain independent source records; the app does not infer a consensus or guess domain/family/repeat/site classes for InterPro, Pfam, or CDD.
- Partial translation mappings may support a continuous amino-acid annotation but are deliberately prohibited from genomic projection. Unresolved mappings are never drawn genomically.
- Whole-genome GRCh38.p14 reference serving is optional. If enabled, the external FASTA and FAI are checksum-declared symlink targets; moving the project requires supplying and registering an equivalent indexed reference rather than editing manifests by hand. Without it, transcript/protein browsing remains available but reference-range requests are unavailable.
- The custom Canvas renderer is the implementation plan's allowed igv.js fallback. It does not include alignment, variant, expression, repeat, conservation, regulatory, cytoband, hosted-genome, or remote-search tracks.
- Screenshot/SVG export of the live Canvas is not a version-1 guarantee; operating-system capture remains the path for an image of the workspace. **Save PDF** instead creates a structured human-readable report with selectable text and vector transcript models, not a Canvas screenshot. It preserves chosen transcripts in the current custom visual order and supports summary, exon/CDS structure, protein-annotation, and exact-sequence sections across either a selected-transcript-union or current-locus scale.
- PDF reports are deliberately bounded to 20 transcripts, 2,000 feature rows, 20,000 total sequence characters, 10,000 characters per excerpt, 100 pages, and 25 MiB. They use exact 1-based inclusive displayed ranges and fail rather than silently truncate. They are not tagged or PDF/UA-conformant, and unsupported characters may be replaced by the portable standard fonts. JSON/TSV remain the machine-oriented export formats.
- Transcript reordering is a visual comparison aid, not a biological ranking or a mutation of GENCODE records. It changes the shared row order only; exports retain the source annotation semantics.
- Manual protein-feature disclosure is additive and capped at 25 rows; a 26th is visibly refused. **View → Default protein tracks → All translated transcripts** instead uses one flag, preserves per-row collapse exceptions (maximum 500), and loads only window/context features. It is not a 25-row subset and does not guarantee source calls for every product.
- Fresh gene navigation follows the saved All/Top/None preference (initially Top). Top is the first translated transcript in annotation order, not a ranking or canonical claim. A gene without a translated product never receives invented protein data. Explicit URLs, Back/Forward state, imported sessions, and restored last views keep their declared content and expansion state.
- Compare adds exact source-call differences to structural/annotation facts. Same accession/method calls are compared as AA-interval multisets, not aligned residues or biological domains gained/lost. It is not an alignment, splice-impact prediction, expression analysis, clinical interpretation, or preference ranking. Loading/error, unavailable source, missing product and unidentified accession remain distinct from valid-empty observations.
- Optional human PPI context is a static BioGRID-backed resource from public SpliceImpactR. Only exact focal-endpoint identifiers are checked against local Pfam/InterPro/ELM calls. Aggregated lists lack original mechanism pairings; unsupported identifiers and partner isoforms/expression are unassessed. Neither observed nor unobserved annotations establish interaction gain/loss, binding affinity, probability or absence. The network date and Ensembl-release match are not asserted. Context has its own hash and exact human annotation-build binding and is never applied to mouse.
- The published `get_ppi_switches()` endpoint-attribution issue is reproducible: in a synthetic GA–GB DDI with focal requirement PF_A and partner requirement PF_B, changing only PF_B in GA is wrongly counted as a changed GB partner despite its recorded focal requirement PF_A being unchanged. This concerns the driver attributed to that interaction, not transcript-domain assignments or GTF geometry. The browser uses the public context resource, not this switch method, and does not patch or vendor package code.
- Comparison CSV/TSV is limited to one gene and 20 selected/comparison/pinned transcripts. It preserves current visual order and includes local notes/tags only in explicitly labeled user fields. It is not a replacement for the authoritative JSON/TSV entity exports or the immutable SQLite package.
- Recents, favorites, last-view restoration, PDF presets, notes, and tags use browser `localStorage`. They are scoped to the loopback origin, browser profile, schema, dataset and annotation build; they do not synchronize across browsers or colleagues, survive all browser-cleaning policies, or provide multi-user conflict resolution. Clearing site data or **Clear saved workspace** removes them.
- The local workspace is capped at 512 KiB. It retains at most 25 recents, 100 favorites, and 500 annotation records; individual notes and tags have their own 5,000-character, 10-tag, and 40-character bounds. Invalid nested entries are ignored, and corrupt/schema/build-mismatched top-level state falls back safely rather than attempting forensic recovery.
- Local user notes/tags are personal interpretation, never GENCODE/Ensembl/HGNC or feature-source evidence. They are not written to the scientific database and are excluded from PDF reports. Portable sessions can transfer them only through an explicit validated merge; same-time or newer conflicting local content is preserved.
- Genomic event highlights are manual context, not variant/splice-effect predictions. Only exact, complete coding maps produce touched-residue positions; introns, UTRs and unresolved products do not. Up to 100 intervals (25 Mb each) are supported. The detailed workspace still shows one selected gene at a time. Highlights are saved in view URLs/sessions but are not written to annotation data or scientific PDF reports.
- Automatic last-view restoration never overrides an explicit URL/deep link. It may appear not to run when restoration is disabled, site storage is unavailable, the build changed, or the page already contains view parameters.
- Quick PDF stores a configuration preset, not a generated PDF or scientific result. Any stale build/transcript/section/source/range condition returns the user to the full bounded dialog; there is no promise that a prior preset applies to a different gene.
- The transcript minimap is a navigation summary of the current shared row layout, not genomic density or biological rank. It appears only for overflowing transcript rows, and its markers identify UI context rather than annotation significance.
- The About/Diagnostics receipt is intentionally support-oriented and allow-listed. It reports the loopback origin and observed resource count but does not prove that a machine is globally offline, and it omits private notes, history, sequences, usernames, and absolute home paths by design.
- Application version `1.2.1` and each annotation build hash are independent. Installing a new interface does not imply new scientific data; conversely, a future annotation package requires its own build identity and validation even if the app version is unchanged.

The application-1.1.2 source engineering gate passed on 2026-07-14 with 32 data, 25 backend/API/PDF, and 112 frontend tests (169 total), plus TypeScript, production build, offline audit, deterministic-build verification, full-package startup, and conflict-copy scan. Its focused search tests cover unique exact gene-symbol precedence, genuine duplicate-symbol ambiguity, same-gene transcript context, exact stable identifiers, prefix-only choice, and empty results. The patch changes no annotation database, schema, or immutable build identity. Native packaging/smoke and active-tree synchronization for 1.1.2 remain unrecorded and must not be inferred from this source gate.

The application-1.1.1 engineering gate passed on 2026-07-14 with 32 data, 25 backend/API/PDF, and 107 frontend tests (164 total), plus TypeScript, production build, offline audit, deterministic-build verification, full-package startup, and conflict-copy scan. Focused frontend coverage includes additive/bounded expansion, default translated-transcript selection, explicit/restored-state precedence, bounded URL/workspace persistence, accessible disclosures, expanded-context retention, demand bounds, and stable asynchronous row geometry. The earlier Chrome 150 SP1/ANK2 workflows at 1280×720/DPR 2, signed native-app smoke, active-tree synchronization, and Release 1 integrity recheck remain part of the release evidence. That single-engine automated interaction and network evidence does not substitute for cross-engine baselines or the human release gates. DPR-1/2 visual/interaction regression still needs Chromium, Firefox, and WebKit; biological interpretation of SP1 and the strand/phase/partial/selenocysteine fixtures needs domain-reviewer sign-off; desktop Safari needs an actual smoke test; and the six section-16.4 usability tasks need an unfamiliar domain scientist. A fresh-environment install replay also remains external evidence. These unchecked items remain listed separately in `docs/release_checklist.md` and must not be represented as completed by the 1.1.1 core gate.
