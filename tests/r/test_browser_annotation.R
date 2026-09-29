# Offline tests of complete model retention and the public SpliceImpactR input.
source("r/browser_annotation.R")
source("r/archive_features.R")
source("r/library_setup.R")
stopifnot(utils::packageVersion("SpliceImpactR") >= "1.0.0")
stopifnot(identical(browser_mart_chromosomes(c("chrX", "chrM", "chr1", "chrY")), c("1", "MT", "X", "Y")))

directory <- tempfile("browser-annotation-test-")
dir.create(directory)
original_libraries <- .libPaths()
test_library <- file.path(directory, "new-personal-library")
stopifnot(identical(ensure_browser_r_library(paths = character(), user_library = test_library), test_library),
          dir.exists(test_library), normalizePath(.libPaths()[[1L]]) == normalizePath(test_library))
stopifnot(identical(ensure_browser_r_library(paths = c(file.path(directory, "absent"), test_library), user_library = ""), test_library))
stopifnot(inherits(try(ensure_browser_r_library(paths = character(), user_library = ""), silent = TRUE), "try-error"))
.libPaths(original_libraries)
row <- function(type, start, end, transcript = NULL, exon = NULL, tsl = NULL,
                biotype = "protein_coding", strand = "+", chr = "chr1", tag = NULL) {
  attributes <- 'gene_id "G.1";'
  if (!is.null(transcript)) attributes <- paste0(attributes, ' transcript_id "', transcript, '"; transcript_type "', biotype, '"; protein_id "P', transcript, '";')
  if (!is.null(exon)) attributes <- paste0(attributes, ' exon_number ', exon, '; exon_id "E', transcript, exon, '.1";')
  if (!is.null(tsl)) attributes <- paste0(attributes, ' transcript_support_level "', tsl, '";')
  if (!is.null(tag)) attributes <- paste0(attributes, ' tag "', tag, '";')
  paste(chr, "test", type, start, end, ".", strand, if (type == "CDS") "0" else ".", attributes, sep = "\t")
}
lines <- row("gene", 100, 1500)
identifiers <- c(paste0("T", 1:5, ".1"), "TMISSING.1", "TNA.1", "TPAR.1_PAR_Y")
tsls <- c(as.character(1:5), NA_character_, "NA", NA_character_)
for (index in seq_along(identifiers)) {
  transcript <- identifiers[[index]]
  start <- 100L + 20L * index
  tsl <- if (is.na(tsls[[index]])) NULL else tsls[[index]]
  biotype <- if (transcript == "TNA.1") "nonsense_mediated_decay" else "protein_coding"
  tag <- if (transcript == "T5.1") "cds_start_NF" else NULL
  lines <- c(lines, row("transcript", start, start + 11L, transcript, tsl = tsl, biotype = biotype, tag = tag),
             row("exon", start, start + 11L, transcript, 1L, tsl, biotype, tag = tag),
             row("CDS", start, start + 8L, transcript, 1L, tsl, biotype, tag = tag))
}
lines <- c(lines,
  row("transcript", 1000, 1206, "TSPLIT.1"),
  row("exon", 1000, 1004, "TSPLIT.1", 1L), row("CDS", 1000, 1004, "TSPLIT.1", 1L),
  row("exon", 1200, 1206, "TSPLIT.1", 2L), row("CDS", 1200, 1206, "TSPLIT.1", 2L),
  row("transcript", 600, 708, "TNEG.1", strand = "-", chr = "chr2"),
  row("exon", 700, 708, "TNEG.1", 1L, strand = "-", chr = "chr2"),
  row("CDS", 700, 707, "TNEG.1", 1L, strand = "-", chr = "chr2"),
  row("exon", 600, 605, "TNEG.1", 2L, strand = "-", chr = "chr2"),
  row("CDS", 600, 603, "TNEG.1", 2L, strand = "-", chr = "chr2")
)
gtf <- file.path(directory, "fixture.gtf")
writeLines(lines, gtf)
annotation <- read_browser_annotation(gtf)
models <- annotation$annotations[type == "transcript"]
stopifnot(nrow(models) == 10L,
          setequal(models$transcript_id, c(browser_stable_id(identifiers), "TSPLIT", "TNEG")),
          models[transcript_id == "TNA", transcript_type] == "nonsense_mediated_decay",
          annotation$inventory$tsl_counts$unscored == 4L)
positive <- annotation$annotations[type == "exon" & transcript_id == "TSPLIT"][order(exon_number)]
negative <- annotation$annotations[type == "exon" & transcript_id == "TNEG"][order(exon_number)]
stopifnot(identical(positive$cds_rel_start, c(1L, 6L)), identical(positive$cds_rel_stop, c(5L, 12L)),
          identical(negative$cds_rel_start, c(1L, 9L)), identical(negative$cds_rel_stop, c(8L, 12L)))

manual <- data.frame(ensembl_transcript_id = c("TSPLIT", "TNEG", "T5", "TMISSING", "TNA"),
  name = "Fixture feature", start = c(2L, 3L, 1L, 1L, 1L), stop = c(2L, 3L, 1L, 1L, 1L), database = "fixture")
features <- SpliceImpactR::get_manual_features(manual, annotation$annotations)
stopifnot(nrow(features) == 5L,
          grepl("chr1:1003-1200", features[ensembl_transcript_id == "TSPLIT", name], fixed = TRUE),
          features[ensembl_transcript_id == "TNEG", strand] == "-")
# Upstream bounding names are provenance only. The Python projection tests
# independently verify exact negative-strand geometry from the raw GTF.
exons <- SpliceImpactR::get_exon_features(annotation$annotations, features, inclusive = TRUE)
stopifnot(nrow(exons[ensembl_transcript_id == "TSPLIT"]) == 2L,
          nrow(exons[ensembl_transcript_id == "TNEG"]) == 2L)

protein_file <- file.path(directory, "proteins.fa")
writeLines(c(">P1.1|T5.1|G.1|example", "ABC", ">P2.1|TMISSING.1|G.1|example", "DEF"), protein_file)
proteins <- read_browser_proteins(protein_file)
stopifnot(identical(proteins$transcript_id, c("T5", "TMISSING")), identical(proteins$protein_seq, c("ABC", "DEF")))

# Direct archive tables preserve distinct accessions at the same interval and
# never use a TSL/biotype selector. Empty feature cells are not transcript rows.
raw <- data.frame(ensembl_transcript_id = c("T5", "T5", "TMISSING"),
  ensembl_peptide_id = c("P1", "P1", "P2"), interpro = c("IPR-A", "IPR-B", ""),
  interpro_short_description = c("A", "B", ""), interpro_description = c("Feature A", "Feature B", ""),
  interpro_start = c(1L, 1L, NA), interpro_end = c(2L, 2L, NA))
long <- browser_long_features(raw, "interpro")
stopifnot(nrow(long) == 2L, identical(long$feature_id, c("IPR-A", "IPR-B")))
stopifnot(nrow(browser_long_features(raw[FALSE, ], "interpro")) == 0L)
processed <- SpliceImpactR::get_manual_features(long, annotation$annotations)
stopifnot(nrow(processed) == 2L)
raw$interpro_start[[1L]] <- 1.5
bad <- try(browser_long_features(raw, "interpro"), silent = TRUE)
stopifnot(inherits(bad, "try-error"))

elm <- browser_confirm_elm(
  data.frame(Primary_Acc = "UNI", ELMIdentifier = "ELM1", Start = 1L, End = 2L),
  data.frame(ELMIdentifier = "ELM1", Regex = "AB"),
  data.frame(uniprotswissprot = c("UNI", "UNI"), ensembl_transcript_id = c("T5", "TMISSING"), ensembl_peptide_id = c("P1", "P2")),
  proteins)
stopifnot(nrow(elm) == 1L, elm$ensembl_transcript_id == "T5")
unlink(directory, recursive = TRUE)
cat("Complete-annotation adapter passed: all TSLs, unscored, other biotypes, incomplete CDS, PAR_Y, both-strand split codons, and non-interactive R library setup.\n")
