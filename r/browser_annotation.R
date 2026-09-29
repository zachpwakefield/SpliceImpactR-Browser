# The browser needs every source transcript, including unscored TSLs and
# incomplete CDS models. SpliceImpactR::get_annotation() filters these models,
# so this adapter uses public Bioconductor readers to construct the input for
# SpliceImpactR::get_manual_features(). No SpliceImpactR internals are used.

BROWSER_ANNOTATION_POLICY <- list(
  transcript_support_level_filter = NULL,
  transcript_biotype_filter = NULL,
  exclude_incomplete_cds = FALSE
)
BROWSER_FEATURE_COLUMNS <- c(
  "ensembl_transcript_id", "start", "stop", "chr", "strand",
  "feature_id", "clean_name", "alt_name", "database",
  "ensembl_peptide_id", "method", "name"
)

# Match the Python builder's identifier convention, including PAR_Y records.
browser_stable_id <- function(value) sub("\\.[0-9]+$", "", as.character(value))

browser_inventory_sha256 <- function(transcript_ids) {
  text <- paste0(paste(sort(unique(transcript_ids), method = "radix"), collapse = "\n"), "\n")
  digest::digest(text, algo = "sha256", serialize = FALSE)
}

read_browser_annotation <- function(gtf_path) {
  tags <- c(
    "gene_id", "transcript_id", "transcript_type", "protein_id",
    "exon_number", "exon_id", "transcript_support_level"
  )
  raw <- data.table::as.data.table(rtracklayer::readGFF(
    gtf_path,
    columns = c("seqid", "type", "start", "end", "strand"),
    tags = tags
  ))
  data.table::setnames(raw, "seqid", "chr")
  for (column in c("gene_id", "transcript_id", "protein_id", "exon_id")) {
    data.table::set(raw, j = column, value = browser_stable_id(raw[[column]]))
  }
  raw[, exon_number := suppressWarnings(as.integer(exon_number))]
  models <- raw[type == "transcript"]
  if (!nrow(models) || anyNA(models$transcript_id) || anyDuplicated(models$transcript_id)) {
    stop("Raw GTF must contain unique, non-missing transcript identifiers.", call. = FALSE)
  }

  # CDS coordinates are 1-based inclusive. GENCODE exon_number follows
  # transcription order on both strands; relative CDS coordinates use that
  # order and retain split codons. The runtime builder validates translation
  # independently and draws genomic features only on exact coding maps.
  coding <- raw[type == "CDS", .(
    cds_gen_start = min(start),
    cds_gen_stop = max(end),
    nt_length = sum(end - start + 1L)
  ), by = .(transcript_id, exon_number)]
  if (anyNA(coding$exon_number) ||
      any(coding$nt_length != coding$cds_gen_stop - coding$cds_gen_start + 1L)) {
    stop("CDS pieces within an exon must form one contiguous interval.", call. = FALSE)
  }
  data.table::setorder(coding, transcript_id, exon_number)
  coding[, cds_rel_stop := cumsum(nt_length), by = transcript_id]
  coding[, cds_rel_start := cds_rel_stop - nt_length + 1L]

  annotation <- raw[type %in% c("gene", "transcript", "exon")]
  annotation[, `:=`(
    cds_has = FALSE,
    cds_gen_start = NA_integer_, cds_gen_stop = NA_integer_,
    cds_rel_start = NA_integer_, cds_rel_stop = NA_integer_
  )]
  annotation[coding, on = .(transcript_id, exon_number), `:=`(
    cds_has = TRUE,
    cds_gen_start = i.cds_gen_start, cds_gen_stop = i.cds_gen_stop,
    cds_rel_start = i.cds_rel_start, cds_rel_stop = i.cds_rel_stop
  )]
  mapped <- annotation[type == "exon" & cds_has == TRUE]
  if (nrow(mapped) != nrow(coding) ||
      any(mapped$cds_gen_start < mapped$start | mapped$cds_gen_stop > mapped$end)) {
    stop("Every CDS interval must lie within exactly one source exon.", call. = FALSE)
  }
  retained_ids <- annotation[type == "transcript", transcript_id]
  if (!setequal(retained_ids, models$transcript_id)) {
    stop("Browser annotation lost source transcript models.", call. = FALSE)
  }
  tsl <- models$transcript_support_level
  tsl[is.na(tsl) | !nzchar(tsl)] <- "unscored"
  list(
    annotations = annotation,
    inventory = list(
      genes = nrow(raw[type == "gene"]),
      transcripts = nrow(models),
      transcript_ids_sha256 = browser_inventory_sha256(retained_ids),
      tsl_counts = as.list(table(tsl))
    )
  )
}

read_browser_proteins <- function(protein_path) {
  proteins <- Biostrings::readAAStringSet(protein_path)
  headers <- strsplit(names(proteins), "|", fixed = TRUE)
  if (any(lengths(headers) < 2L)) {
    stop("Protein FASTA headers must contain protein and transcript identifiers.", call. = FALSE)
  }
  data.table::data.table(
    protein_id = browser_stable_id(vapply(headers, `[[`, character(1), 1L)),
    transcript_id = browser_stable_id(vapply(headers, `[[`, character(1), 2L)),
    protein_seq = as.character(proteins)
  )
}

normalize_browser_features <- function(features, source) {
  features <- as.data.frame(features, stringsAsFactors = FALSE)
  if (!nrow(features) && !ncol(features)) {
    features <- setNames(rep(list(character()), length(BROWSER_FEATURE_COLUMNS)), BROWSER_FEATURE_COLUMNS)
    features <- as.data.frame(features, stringsAsFactors = FALSE)
  }
  missing <- setdiff(BROWSER_FEATURE_COLUMNS, names(features))
  if (length(missing)) {
    stop(source, " output is missing columns: ", paste(missing, collapse = ", "), call. = FALSE)
  }
  features <- features[BROWSER_FEATURE_COLUMNS]
  if (anyNA(features$ensembl_transcript_id) || any(!nzchar(features$ensembl_transcript_id))) {
    stop(source, " output contains a missing transcript identifier.", call. = FALSE)
  }
  features
}

browser_feature_receipt <- function(path, features) {
  list(
    file = basename(path),
    sha256 = digest::digest(file = path, algo = "sha256"),
    size = unname(file.info(path)$size),
    rows = nrow(features),
    distinct_transcripts = length(unique(features$ensembl_transcript_id)),
    distinct_feature_ids = length(unique(features$feature_id[!is.na(features$feature_id)]))
  )
}

write_browser_json <- function(value, path) {
  temporary <- tempfile(pattern = ".receipt-", tmpdir = dirname(path))
  on.exit(unlink(temporary), add = TRUE)
  jsonlite::write_json(value, temporary, pretty = TRUE, auto_unbox = TRUE, null = "null")
  if (!file.rename(temporary, path)) stop("Cannot publish receipt: ", basename(path), call. = FALSE)
}
