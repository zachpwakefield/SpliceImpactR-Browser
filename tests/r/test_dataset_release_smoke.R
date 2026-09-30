#!/usr/bin/env Rscript
# Real-release, gene-scoped retrieval checkpoint. This is NOT a full database
# build or proof of exact nucleotide-to-protein genomic projection.
options(stringsAsFactors = FALSE, timeout = max(600L, getOption("timeout", 60L)))
run_release_checkpoint <- function() {
arguments <- commandArgs(trailingOnly = TRUE)
args <- list()
index <- 1L
while (index <= length(arguments)) {
  key <- arguments[[index]]
  if (key %in% c("-h", "--help")) {
    cat("Usage: Rscript tests/r/test_dataset_release_smoke.R --dataset ID --gtf FILE --protein-fa FILE --gene SYMBOL --output JSON\n",
        "Verifies full official input bytes, retains all raw gene models, and queries their release-matched features.\n",
        "The temporary gene slice and proof are not accepted as full preparation receipts.\n", sep = "")
    quit(status = 0L)
  }
  name <- sub("^--", "", key)
  if (!startsWith(key, "--") || !name %in% c("dataset", "gtf", "protein-fa", "gene", "output") ||
      name %in% names(args) || index == length(arguments) || startsWith(arguments[[index + 1L]], "--")) {
    stop("Unknown, repeated, or valueless argument: ", key, call. = FALSE)
  }
  args[[name]] <- arguments[[index + 1L]]
  index <- index + 2L
}
required <- c("dataset", "gtf", "protein-fa", "gene", "output")
if (!all(required %in% names(args)) || !grepl("^[A-Za-z0-9_.-]+$", args$gene)) {
  stop("Supply --dataset, --gtf, --protein-fa, --gene, --output. Gene symbols must be plain identifiers.", call. = FALSE)
}
script_flag <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
root <- dirname(dirname(dirname(normalizePath(sub("^--file=", "", script_flag[[1L]]), mustWork = TRUE))))
source(file.path(root, "r", "datasets.R"))
source(file.path(root, "r", "browser_annotation.R"))
source(file.path(root, "r", "archive_features.R"))
registry <- read_browser_dataset_profiles(file.path(root, "backend", "data", "dataset_profiles.json"))
profile <- browser_dataset_profile(registry, args$dataset)
gtf <- browser_verify_raw_asset(args$gtf, profile, "gtf")
protein_file <- browser_verify_raw_asset(args$`protein-fa`, profile, "translations")
browser_validate_gtf_header(gtf, profile)
directory <- tempfile("release-gene-checkpoint-")
dir.create(directory)
on.exit(unlink(directory, recursive = TRUE), add = TRUE)
slice <- file.path(directory, "gene.gtf")
reader <- gzfile(gtf, open = "rt")
writer <- file(slice, open = "wt")
pattern <- paste0('gene_name "', args$gene, '";')
raw_selected_rows <- 0L
repeat {
  lines <- readLines(reader, n = 20000L, warn = FALSE)
  if (!length(lines)) break
  comments <- startsWith(lines, "#")
  selected <- grepl(pattern, lines, fixed = TRUE) & !comments
  if (any(comments)) writeLines(lines[comments], writer)
  if (any(selected)) {
    writeLines(lines[selected], writer)
    raw_selected_rows <- raw_selected_rows + sum(selected)
  }
}
close(reader)
close(writer)
if (!raw_selected_rows) stop("Gene symbol is absent from the verified raw GTF: ", args$gene, call. = FALSE)
annotation <- read_browser_annotation(slice)
models <- annotation$annotations[type == "transcript"]
if (annotation$inventory$genes != 1L || !nrow(models) ||
    any(!startsWith(models$transcript_id, profile$identifier_prefixes$transcript))) {
  stop("Gene symbol must resolve to one source gene with the selected species identifiers.", call. = FALSE)
}
sequences <- read_browser_proteins(protein_file, profile)
sequences <- sequences[transcript_id %in% models$transcript_id]
message("Verified ", profile$dataset_id, " / ", args$gene, ": ", nrow(models), " raw transcripts and ",
        nrow(sequences), " translations. No TSL/biotype/completeness filters.")
mart <- browser_archive_mart(profile)
available <- biomaRt::listAttributes(mart)$name
query_log <- list()
query <- function(attributes, filters, values, mart, useCache) {
  if (!identical(filters, "chromosome_name")) stop("Unexpected adapter selector in release checkpoint.")
  chromosomes <- browser_mart_chromosomes(models$chr)
  if (!all(as.character(values) %in% chromosomes)) stop("Checkpoint requested an unrelated chromosome.")
  ids <- models$transcript_id
  # A one-gene slice normally occupies one chromosome. For rare multi-region
  # models restrict to the raw IDs belonging to the requested chromosome.
  if (length(chromosomes) > 1L) {
    model_chromosomes <- sub("^chr", "", models$chr)
    model_chromosomes[model_chromosomes == "M"] <- "MT"
    ids <- models$transcript_id[model_chromosomes %in% as.character(values)]
  } else ids <- models$transcript_id
  query_log[[length(query_log) + 1L]] <<- list(filters = "ensembl_transcript_id",
                                             requested_transcripts = length(ids))
  biomaRt::getBM(attributes = attributes, filters = "ensembl_transcript_id",
                 values = ids, mart = mart, useCache = useCache)
}
sources <- c("interpro", "pfam", "cdd", "tmhmm", "signalp", "mobidblite", "elm")
tables <- list()
receipts <- list()
for (source in sources) {
  features <- browser_archive_features(source, annotation$annotations, sequences, mart, directory,
                                        profile, query = query, available_attributes = available)
  retrieval <- attr(features, "browser_retrieval")
  features <- normalize_browser_features(features, source)
  if (any(!features$ensembl_transcript_id %in% models$transcript_id)) {
    stop("Feature source introduced a transcript outside the complete raw gene catalog.", call. = FALSE)
  }
  tables[[source]] <- features
  receipts[[source]] <- list(status = retrieval$status, reason = retrieval$reason,
                            rows = nrow(features), distinct_transcripts = length(unique(features$ensembl_transcript_id)),
                            retrieval = retrieval)
}
features <- data.table::as.data.table(do.call(rbind, tables))
coding <- annotation$annotations[type == "exon" & cds_has == TRUE,
                                 .(cds_length_aa = floor(max(cds_rel_stop) / 3L)), by = transcript_id]
checked <- merge(features, coding, by.x = "ensembl_transcript_id", by.y = "transcript_id", all.x = TRUE)
checked <- merge(checked, sequences[, .(ensembl_transcript_id = transcript_id,
                                        ensembl_peptide_id = protein_id, protein_length_aa = nchar(protein_seq))],
                 by = c("ensembl_transcript_id", "ensembl_peptide_id"), all.x = TRUE)
checked[, `:=`(
  translation_identity_status = ifelse(!is.na(protein_length_aa), "matched-transcript-and-peptide",
    ifelse(ensembl_transcript_id %in% sequences$transcript_id, "peptide-identity-mismatch", "missing-transcript-translation")),
  outside_source_cds = !is.na(cds_length_aa) & (start > cds_length_aa | stop > cds_length_aa),
  outside_supplied_translation = !is.na(protein_length_aa) & (start > protein_length_aa | stop > protein_length_aa)
)]
exceptions <- checked[outside_source_cds | outside_supplied_translation]
invalid <- checked[outside_supplied_translation]
nonprojectable <- checked[outside_source_cds & !outside_supplied_translation]
translation_issues <- checked[translation_identity_status != "matched-transcript-and-peptide"]
ids_before <- sort(models$transcript_id, method = "radix")
ids_after <- sort(annotation$annotations[type == "transcript", transcript_id], method = "radix")
stopifnot(identical(ids_before, ids_after))
output <- normalizePath(args$output, winslash = "/", mustWork = FALSE)
dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
write_browser_json(list(
  schema = "transcript-browser-release-gene-checkpoint/v1",
  scope = "gene-retrieval-only-not-full-preparation-or-genomic-projection-validation",
  dataset_id = profile$dataset_id, species = profile$species, gencode_release = profile$gencode_release,
  ensembl_release = profile$ensembl_release, assembly = profile$assembly, biomart = profile$biomart,
  gene = args$gene, annotation_policy = BROWSER_ANNOTATION_POLICY,
  raw_inputs = list(
    gtf = list(file = profile$raw_inputs$gtf$file, md5 = profile$raw_inputs$gtf$md5),
    translations = list(file = profile$raw_inputs$translations$file, md5 = profile$raw_inputs$translations$md5)),
  derived_gene_slice = list(rows = raw_selected_rows, sha256 = digest::digest(file = slice, algo = "sha256")),
  annotation_inventory = annotation$inventory,
  transcripts = as.data.frame(models[, .(transcript_id, transcript_type, transcript_support_level)]),
  translations = as.data.frame(sequences[, .(transcript_id, protein_id, length_aa = nchar(protein_seq))]),
  source_status = receipts, feature_rows = as.data.frame(features),
  original_intervals_preserved = TRUE,
  invalid_source_intervals = as.data.frame(invalid),
  nonprojectable_cds_intervals = as.data.frame(nonprojectable),
  source_interval_exceptions = as.data.frame(exceptions),
  translation_identity_issues = as.data.frame(translation_issues),
  exact_genomic_projection_validated = FALSE,
  feature_query_policy = list(transcript_support_level_filter = NULL, transcript_biotype_filter = NULL,
                              selectors = query_log, complete_raw_gene_catalog_retained = TRUE),
  producer = list(package = "SpliceImpactR", version = as.character(utils::packageVersion("SpliceImpactR"))),
  note = paste("No paths or workstation identifiers are recorded. All source intervals remain original.",
               "A feature beyond the supplied protein is invalid; a feature within the protein but beyond the source CDS is nonprojectable.",
               "Missing translation or peptide-identity mismatch is not a validated match. Exact genomic projection is not tested here.")
), output)
unlink(directory, recursive = TRUE)
cat("Release-backed gene checkpoint passed: ", profile$dataset_id, " / ", args$gene,
    " / ", nrow(models), " transcripts / ", nrow(features), " feature rows / ",
    nrow(exceptions), " explicitly flagged source-range exceptions / ",
    nrow(translation_issues), " feature-translation identity issues.\n", sep = "")
}
run_release_checkpoint()
