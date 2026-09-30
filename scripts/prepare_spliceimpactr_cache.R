#!/usr/bin/env Rscript

# Prepare complete source models and SpliceImpactR protein-feature tables.
# The browser annotation is never filtered by TSL, biotype, or CDS tags.
options(stringsAsFactors = FALSE)
options(timeout = max(600, getOption("timeout", 60)))

parse_args <- function(values) {
  allowed <- c("output", "dataset", "base-dir", "gtf", "transcript-fa", "protein-fa", "force", "skip-exon", "list-datasets")
  result <- list()
  index <- 1L
  while (index <= length(values)) {
    key <- values[[index]]
    if (key %in% c("--help", "-h")) {
      cat(paste(
        "Usage: Rscript scripts/prepare_spliceimpactr_cache.R --output DIR [options]",
        "  --dataset ID         Reviewed species/GENCODE/Ensembl profile (default: human-gencode-v45)",
        "  --list-datasets      Print reviewed profiles and exit",
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
    if (name %in% c("force", "skip-exon", "list-datasets")) {
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

script_flag <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_flag[[1L]]), mustWork = TRUE)
project_root <- dirname(dirname(script_path))
dataset_adapter_path <- file.path(project_root, "r", "datasets.R")
source(dataset_adapter_path)
profile_path <- file.path(project_root, "backend", "data", "dataset_profiles.json")
if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("Missing R package: jsonlite. Run ./scripts/install_spliceimpactr.sh first.", call. = FALSE)
}
registry <- read_browser_dataset_profiles(profile_path)
if (isTRUE(args$`list-datasets`)) {
  for (profile in registry$profiles) {
    cat(profile$dataset_id, " | ", profile$species, " | GENCODE ", profile$gencode_release,
        " | Ensembl ", profile$ensembl_release, " | ", profile$assembly, "\n", sep = "")
  }
  quit(status = 0L)
}
if (is.null(args$output) || !nzchar(args$output)) stop("--output DIR is required.", call. = FALSE)
profile <- browser_dataset_profile(registry, get_arg("dataset", registry$default_dataset_id))
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

explicit <- c(gtf = get_arg("gtf", NA_character_), transcripts = get_arg("transcript-fa", NA_character_), translations = get_arg("protein-fa", NA_character_))
if (anyNA(explicit) && !all(is.na(explicit))) {
  stop("Provide all three of --gtf, --transcript-fa, and --protein-fa, or none.", call. = FALSE)
}

message("[1/4] Resolving unmodified ", profile$label, " files (Ensembl ", profile$ensembl_release, ")")
raw <- browser_resolve_raw_assets(profile, output_dir, base_dir, explicit)
raw_receipts <- raw$receipts

message("[2/4] Preparing every source transcript, including unscored TSLs and incomplete CDS models")
annotation <- read_browser_annotation(raw$paths[["gtf"]], profile)
sequences <- read_browser_proteins(raw$paths[["translations"]], profile)
sources <- c("interpro", "pfam", "cdd", "tmhmm", "signalp", "mobidblite", "elm")
producer <- list(
  package = "SpliceImpactR", version = as.character(utils::packageVersion("SpliceImpactR")),
  bioconductor_version = as.character(BiocManager::version()),
  r_version = as.character(getRversion()), package_license = "GPL-3",
  adapter = "complete-raw-gtf/v2"
)
code_hashes <- list(
  prepare = digest::digest(file = script_path, algo = "sha256"),
  annotation_adapter = digest::digest(file = adapter_path, algo = "sha256"),
  feature_adapter = digest::digest(file = feature_adapter_path, algo = "sha256"),
  dataset_adapter = digest::digest(file = dataset_adapter_path, algo = "sha256"),
  dataset_profiles = digest::digest(file = profile_path, algo = "sha256")
)
feature_query_policy <- list(
  biomart_transcript_biotype_filter = NULL,
  provider = paste0("explicit-release-", profile$ensembl_release, "-archive/public-biomaRt"),
  normalization_api = "SpliceImpactR::get_manual_features",
  annotation_models_removed = FALSE,
  test_fixture = FALSE, combine_overlaps = FALSE, source_coordinates_preserved = TRUE,
  note = paste("BioMart queries have no biotype or TSL selector; no feature result is required to retain a transcript.",
               "The validated SpliceImpactR 1.0.0 get_protein_features path filters biotypes, collapses coincident accessions, and clips intervals;",
               "the public biomaRt/get_manual_features adapter preserves original source intervals and distinct accessions.")
)
signature <- digest::digest(jsonlite::toJSON(list(
  raw_inputs = raw_receipts, producer = producer, code_hashes = code_hashes,
  annotation_policy = BROWSER_ANNOTATION_POLICY, inventory = annotation$inventory,
  dataset = profile
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
    if (is.null(mart)) mart <- browser_archive_mart(profile)
    features <- browser_archive_features(source_name, annotation$annotations, sequences,
      mart, base_dir, profile, force = force)
  }
  retrieval <- if (reusable) old$retrieval else attr(features, "browser_retrieval")
  features <- normalize_browser_features(features, source_name)
  if (is.null(retrieval$status) || !retrieval$status %in% c("available", "available-empty", "unavailable")) {
    stop("Feature source lacks an explicit availability status: ", source_name, call. = FALSE)
  }
  if (source_name %in% c("interpro", "pfam") && !identical(retrieval$status, "unavailable") && !nrow(features)) {
    stop("The full ", profile$species, " ", source_name, " query returned no features; retry preparation.", call. = FALSE)
  }
  if (!reusable) {
    temporary <- tempfile(pattern = ".features-", tmpdir = output_dir)
    saveRDS(features, temporary, compress = "xz")
    if (!file.rename(temporary, output_path)) stop("Cannot publish ", basename(output_path), call. = FALSE)
  }
  receipt <- browser_feature_receipt(output_path, features)
  receipt$status <- retrieval$status
  if (!is.null(retrieval$reason)) receipt$reason <- retrieval$reason
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
  schema = "transcript-browser-spliceimpactr-cache/v3",
  dataset_id = profile$dataset_id, species = profile$species,
  gencode_release = profile$gencode_release, ensembl_release = profile$ensembl_release, assembly = profile$assembly,
  biomart = profile$biomart,
  annotation_policy = BROWSER_ANNOTATION_POLICY, annotation_inventory = annotation$inventory,
  raw_inputs = raw_receipts, raw_accession = raw$accession, feature_sources = feature_summary,
  exon_features = exon_summary, producer = producer, feature_query_policy = feature_query_policy, code_hashes = code_hashes,
  required_feature_columns = BROWSER_FEATURE_COLUMNS,
  note = "All paths are relative. Counts and digests describe this preparation, not a workstation-specific cache."
), file.path(output_dir, "spliceimpactr_manifest.json"))
message("Prepared complete browser inputs in: ", output_dir)
