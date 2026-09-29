#!/usr/bin/env Rscript

# Prepare complete source models and SpliceImpactR protein-feature tables.
# The browser annotation is never filtered by TSL, biotype, or CDS tags.
options(stringsAsFactors = FALSE)
options(timeout = max(600, getOption("timeout", 60)))

parse_args <- function(values) {
  allowed <- c("output", "base-dir", "gtf", "transcript-fa", "protein-fa", "force", "skip-exon")
  result <- list()
  index <- 1L
  while (index <= length(values)) {
    key <- values[[index]]
    if (key %in% c("--help", "-h")) {
      cat(paste(
        "Usage: Rscript scripts/prepare_spliceimpactr_cache.R --output DIR [options]",
        "  --base-dir DIR       Download/query cache (default: sibling spliceimpactr-cache)",
        "  --gtf FILE --transcript-fa FILE --protein-fa FILE   Use all three existing raw files",
        "  --force              Refresh remote feature queries and local outputs",
        "  --skip-exon          Omit the optional derived exon audit table",
        "All source transcript models are retained; there is no TSL/biotype filter.",
        sep = "\n"
      ), "\n")
      quit(status = 0L)
    }
    name <- sub("^--", "", key)
    if (!startsWith(key, "--") || !name %in% allowed || name %in% names(result)) {
      stop("Unknown or repeated argument: ", key, ". Use --help.", call. = FALSE)
    }
    if (name %in% c("force", "skip-exon")) {
      result[[name]] <- TRUE
      index <- index + 1L
    } else {
      if (index == length(values) || startsWith(values[[index + 1L]], "--")) {
        stop("Missing value for ", key, call. = FALSE)
      }
      result[[name]] <- values[[index + 1L]]
      index <- index + 2L
    }
  }
  result
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
get_arg <- function(name, default = NULL) if (is.null(args[[name]])) default else args[[name]]
if (is.null(args$output) || !nzchar(args$output)) stop("--output DIR is required.", call. = FALSE)

script_flag <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_flag[[1L]]), mustWork = TRUE)
project_root <- dirname(dirname(script_path))
adapter_path <- file.path(project_root, "r", "browser_annotation.R")
source(adapter_path)
feature_adapter_path <- file.path(project_root, "r", "archive_features.R")
source(feature_adapter_path)

packages <- c("SpliceImpactR", "BiocManager", "BiocFileCache", "rtracklayer", "Biostrings", "biomaRt", "httr", "data.table", "jsonlite", "digest")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop("Missing R packages: ", paste(missing, collapse = ", "),
       ". Run ./scripts/install_spliceimpactr.sh first.", call. = FALSE)
}
if (utils::packageVersion("SpliceImpactR") < "1.0.0") {
  stop("Use the released Bioconductor SpliceImpactR package (>= 1.0.0). Run ./scripts/install_spliceimpactr.sh with R 4.6 or later.", call. = FALSE)
}

output_dir <- normalizePath(args$output, winslash = "/", mustWork = FALSE)
base_dir <- normalizePath(get_arg("base-dir", file.path(output_dir, "..", "spliceimpactr-cache")), winslash = "/", mustWork = FALSE)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(base_dir, recursive = TRUE, showWarnings = FALSE)
force <- isTRUE(args$force)

raw_names <- c(
  gtf = "gencode.v45.annotation.gtf.gz",
  transcript = "gencode.v45.pc_transcripts.fa.gz",
  translation = "gencode.v45.pc_translations.fa.gz"
)
raw_md5 <- c(
  gtf = "b6eeb6c9791b7a43a5504a654ff09d9a",
  transcript = "229d2da3b0dc7e83dd8ae69034be1169",
  translation = "cf7b19def48b2235abde68df419b4b03"
)
explicit <- c(gtf = get_arg("gtf", NA_character_), transcript = get_arg("transcript-fa", NA_character_), translation = get_arg("protein-fa", NA_character_))
if (anyNA(explicit) && !all(is.na(explicit))) {
  stop("Provide all three of --gtf, --transcript-fa, and --protein-fa, or none.", call. = FALSE)
}

message("[1/4] Resolving the unmodified GENCODE v45 files")
bfc <- NULL
raw_receipts <- list()
for (key in names(raw_names)) {
  filename <- raw_names[[key]]
  destination <- file.path(output_dir, filename)
  if (!is.na(explicit[[key]])) {
    input <- normalizePath(explicit[[key]], mustWork = TRUE)
  } else if (file.exists(destination) && identical(unname(tools::md5sum(destination)), raw_md5[[key]])) {
    input <- destination
  } else {
    if (is.null(bfc)) bfc <- BiocFileCache::BiocFileCache(file.path(base_dir, "BiocFileCache"), ask = FALSE)
    cache_key <- paste0("transcript-browser/gencode/v45/", filename)
    hits <- BiocFileCache::bfcquery(bfc, cache_key, field = "rname", exact = TRUE)
    if (!nrow(hits)) {
      downloaded <- BiocFileCache::bfcadd(bfc, rname = cache_key,
        fpath = paste0("https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_45/", filename), rtype = "web")
      input <- unname(downloaded[[1L]])
    } else {
      if (nrow(hits) != 1L) stop("Ambiguous raw download cache entry: ", filename, call. = FALSE)
      input <- unname(BiocFileCache::bfcpath(bfc, hits$rid))
      if (!file.exists(input) || !identical(unname(tools::md5sum(input)), raw_md5[[key]])) {
        BiocFileCache::bfcdownload(bfc, hits$rid, ask = FALSE)
        input <- unname(BiocFileCache::bfcpath(bfc, hits$rid))
      }
    }
  }
  actual <- unname(tools::md5sum(input))
  if (!identical(actual, raw_md5[[key]])) stop("Wrong GENCODE bytes for ", filename, ": expected MD5 ", raw_md5[[key]], "; found ", actual, call. = FALSE)
  if (!identical(normalizePath(input), normalizePath(destination, mustWork = FALSE))) {
    if (!file.copy(input, destination, overwrite = TRUE)) stop("Cannot copy ", filename, call. = FALSE)
  }
  raw_receipts[[filename]] <- list(file = filename, md5 = actual, size = unname(file.info(destination)$size))
}

message("[2/4] Preparing every source transcript, including unscored TSLs and incomplete CDS models")
annotation <- read_browser_annotation(file.path(output_dir, raw_names[["gtf"]]))
if (annotation$inventory$genes != 63187L || annotation$inventory$transcripts != 252930L) {
  stop("The GENCODE v45 gene/transcript inventory is incomplete.", call. = FALSE)
}
sequences <- read_browser_proteins(file.path(output_dir, raw_names[["translation"]]))
sources <- c("interpro", "pfam", "cdd", "tmhmm", "signalp", "mobidblite", "elm")
producer <- list(
  package = "SpliceImpactR", version = as.character(utils::packageVersion("SpliceImpactR")),
  bioconductor_version = as.character(BiocManager::version()),
  r_version = as.character(getRversion()), package_license = "GPL-3",
  adapter = "complete-raw-gtf/v1"
)
code_hashes <- list(
  prepare = digest::digest(file = script_path, algo = "sha256"),
  annotation_adapter = digest::digest(file = adapter_path, algo = "sha256"),
  feature_adapter = digest::digest(file = feature_adapter_path, algo = "sha256")
)
feature_query_policy <- list(
  biomart_transcript_biotype_filter = NULL,
  provider = "explicit-release-111-archive/public-biomaRt",
  normalization_api = "SpliceImpactR::get_manual_features",
  annotation_models_removed = FALSE,
  test_fixture = FALSE, combine_overlaps = FALSE,
  note = "BioMart queries have no biotype or TSL selector; no feature result is required to retain a transcript."
)
signature <- digest::digest(jsonlite::toJSON(list(
  raw_inputs = raw_receipts, producer = producer, code_hashes = code_hashes,
  annotation_policy = BROWSER_ANNOTATION_POLICY, inventory = annotation$inventory,
  ensembl_release = 111L
), auto_unbox = TRUE, null = "null"), algo = "sha256", serialize = FALSE)

message("[3/4] Querying seven SpliceImpactR feature sources against the complete annotation")
Sys.setenv(BIOMART_CACHE = file.path(base_dir, "biomart"))
mart <- NULL
feature_summary <- list()
feature_tables <- list()
for (source_name in sources) {
  output_path <- file.path(output_dir, paste0(source_name, ".rds"))
  receipt_path <- file.path(output_dir, paste0(source_name, ".receipt.json"))
  reusable <- FALSE
  if (!force && file.exists(output_path) && file.exists(receipt_path)) {
    old <- tryCatch(jsonlite::read_json(receipt_path, simplifyVector = TRUE), error = function(e) NULL)
    reusable <- !is.null(old) && identical(old$signature, signature) &&
      identical(old$sha256, digest::digest(file = output_path, algo = "sha256"))
  }
  if (reusable) {
    message("  [verified cache] ", source_name)
    features <- readRDS(output_path)
  } else {
    message("  [query] ", source_name)
    if (is.null(mart)) mart <- browser_archive_mart()
    features <- browser_archive_features(source_name, annotation$annotations, sequences,
      mart, base_dir, force = force)
  }
  retrieval <- if (reusable) old$retrieval else attr(features, "browser_retrieval")
  features <- normalize_browser_features(features, source_name)
  if (source_name %in% c("interpro", "pfam") && !nrow(features)) {
    stop("The full human ", source_name, " query returned no features; retry preparation.", call. = FALSE)
  }
  if (!reusable) {
    temporary <- tempfile(pattern = ".features-", tmpdir = output_dir)
    saveRDS(features, temporary, compress = "xz")
    if (!file.rename(temporary, output_path)) stop("Cannot publish ", basename(output_path), call. = FALSE)
  }
  receipt <- browser_feature_receipt(output_path, features)
  receipt$retrieval <- retrieval
  write_browser_json(c(list(signature = signature), receipt), receipt_path)
  feature_summary[[source_name]] <- receipt
  feature_tables[[source_name]] <- features
}

message("[4/4] Publishing preparation provenance")
exon_summary <- NULL
if (!isTRUE(args$`skip-exon`)) {
  message("  [derive] optional exon-level audit (the browser recomputes exact projections independently)")
  exon_features <- SpliceImpactR::get_exon_features(annotation$annotations, do.call(rbind, feature_tables), inclusive = TRUE)
  exon_path <- file.path(output_dir, "exon_features.rds")
  temporary <- tempfile(pattern = ".exons-", tmpdir = output_dir)
  saveRDS(exon_features, temporary, compress = "xz")
  if (!file.rename(temporary, exon_path)) stop("Cannot publish exon audit.", call. = FALSE)
  exon_summary <- list(file = basename(exon_path), rows = nrow(exon_features), sha256 = digest::digest(file = exon_path, algo = "sha256"))
}
write_browser_json(list(
  schema = "transcript-browser-spliceimpactr-cache/v2",
  gencode_release = 45L, ensembl_release = 111L, assembly = "GRCh38.p14",
  annotation_policy = BROWSER_ANNOTATION_POLICY, annotation_inventory = annotation$inventory,
  raw_inputs = raw_receipts, feature_sources = feature_summary,
  exon_features = exon_summary, producer = producer, feature_query_policy = feature_query_policy, code_hashes = code_hashes,
  required_feature_columns = BROWSER_FEATURE_COLUMNS,
  note = "All paths are relative. Counts and digests describe this preparation, not a workstation-specific cache."
), file.path(output_dir, "spliceimpactr_manifest.json"))
message("Prepared complete browser inputs in: ", output_dir)
