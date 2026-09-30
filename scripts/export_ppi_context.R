#!/usr/bin/env Rscript

# Optional human gene-level interaction context. This exporter deliberately
# never calls get_ppi_switches(): context is not an isoform PPI prediction.

browser_ppi_annotation_binding <- function(manifest, profile) {
  if (!identical(profile$species, "human")) {
    stop("SpliceImpactR's bundled PPI context is human-only; mouse is not supported.", call. = FALSE)
  }
  if (!is.list(manifest)) stop("Invalid annotation manifest.", call. = FALSE)
  aliases <- function(keys) manifest[intersect(keys, names(manifest))]
  identifiers <- aliases(c("dataset_id", "datasetId"))
  legacy <- !length(identifiers)
  if (legacy && !identical(profile$dataset_id, "human-gencode-v45")) {
    stop("Only the verified legacy human-v45 manifest may omit its dataset identifier.", call. = FALSE)
  }
  if (length(identifiers) && any(!vapply(identifiers, identical, logical(1), y = profile$dataset_id))) {
    stop("Annotation manifest dataset does not match --dataset.", call. = FALSE)
  }
  releases <- aliases(c("gencode_release", "gencodeRelease", "release"))
  accepted_release <- c(as.character(profile$gencode_release), paste0("GENCODE v", profile$gencode_release))
  if (!length(releases) || any(!vapply(releases, function(value) {
    length(value) == 1L && !is.na(value) && as.character(value) %in% accepted_release
  }, logical(1)))) stop("Annotation GENCODE release does not match the selected profile.", call. = FALSE)
  ensembl <- aliases(c("ensembl_release", "ensemblRelease"))
  if (!length(ensembl) || any(!vapply(ensembl, function(value) {
    length(value) == 1L && !is.na(value) && identical(as.character(value), as.character(profile$ensembl_release))
  }, logical(1)))) stop("Annotation Ensembl release does not match the selected profile.", call. = FALSE)
  if (!identical(manifest$assembly, profile$assembly)) {
    stop("Annotation assembly does not match the selected profile.", call. = FALSE)
  }
  species <- manifest$species
  if (is.null(species) && legacy) species <- "human"
  if (!identical(species, "human")) stop("Annotation species must explicitly match human.", call. = FALSE)
  hashes <- aliases(c("build_hash", "buildHash"))
  if (!length(hashes) || any(!vapply(hashes, function(value) {
    is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9a-f]{64}$", value)
  }, logical(1))) || any(!vapply(hashes, identical, logical(1), y = hashes[[1L]]))) {
    stop("Annotation manifest requires one consistent SHA256 build hash.", call. = FALSE)
  }
  list(dataset_id = profile$dataset_id, species = profile$species,
       gencode_release = profile$gencode_release, ensembl_release = profile$ensembl_release,
       assembly = profile$assembly, annotation_build_hash = hashes[[1L]])
}

browser_ppi_validate_table <- function(interactions) {
  columns <- c("geneA", "geneB", "biogrid", "DDI", "DMI", "DDI_A", "DDI_B", "DMI_A", "DMI_B")
  if (!is.data.frame(interactions) || !setequal(names(interactions), columns) ||
      anyDuplicated(names(interactions)) || nrow(interactions) < 1L) {
    stop("Unsupported public get_ppi_interactions() table schema; no export was written.", call. = FALSE)
  }
  for (field in c("geneA", "geneB")) {
    value <- interactions[[field]]
    if (!is.character(value) || anyNA(value) || any(!grepl("^ENSG[0-9]{11}$", value))) {
      stop("PPI endpoints must be stable, versionless human Ensembl gene identifiers.", call. = FALSE)
    }
  }
  for (field in c("biogrid", "DDI", "DMI")) {
    if (!is.logical(interactions[[field]]) || anyNA(interactions[[field]])) {
      stop("PPI evidence flags must be non-missing logical values: ", field, call. = FALSE)
    }
  }
  for (field in c("DDI_A", "DDI_B", "DMI_A", "DMI_B")) {
    value <- interactions[[field]]
    valid <- function(tokens) {
      is.null(tokens) || (is.character(tokens) && !anyNA(tokens) && all(nzchar(tokens)))
    }
    if (!is.list(value) || length(value) != nrow(interactions) || !all(vapply(value, valid, logical(1)))) {
      stop("PPI endpoint tokens must be character arrays or empty lists: ", field, call. = FALSE)
    }
  }
  for (kind in c("DDI", "DMI")) {
    a <- lengths(interactions[[paste0(kind, "_A")]])
    b <- lengths(interactions[[paste0(kind, "_B")]])
    flag <- interactions[[kind]]
    if (any((flag & (a == 0L | b == 0L)) | (!flag & (a > 0L | b > 0L)))) {
      stop("PPI evidence flags contradict their endpoint-owned token arrays: ", kind, call. = FALSE)
    }
  }
  invisible(TRUE)
}

browser_ppi_write_ndjson <- function(interactions, path, chunk_size = 5000L) {
  browser_ppi_validate_table(interactions)
  if (length(chunk_size) != 1L || !is.numeric(chunk_size) || is.na(chunk_size) ||
      chunk_size < 1 || chunk_size != floor(chunk_size)) stop("Invalid NDJSON chunk size.", call. = FALSE)
  output <- file(path, open = "wb")
  on.exit(close(output), add = TRUE)
  fields <- c(ddiA = "DDI_A", ddiB = "DDI_B", dmiA = "DMI_A", dmiB = "DMI_B")
  for (first in seq.int(1L, nrow(interactions), by = chunk_size)) {
    rows <- seq.int(first, min(first + chunk_size - 1L, nrow(interactions)))
    page <- data.frame(geneA = interactions$geneA[rows], geneB = interactions$geneB[rows],
                       biogrid = interactions$biogrid[rows], ddi = interactions$DDI[rows],
                       dmi = interactions$DMI[rows], stringsAsFactors = FALSE)
    for (field in names(fields)) {
      # AsIs prevents a singleton identifier from becoming a scalar string.
      # Genuine source NULL is the documented empty-set representation, not
      # an unknown value; NA is rejected above instead of silently removed.
      page[[field]] <- lapply(interactions[[fields[[field]]]][rows], function(tokens) {
        I(if (is.null(tokens)) character() else tokens)
      })
    }
    jsonlite::stream_out(page, output, verbose = FALSE, auto_unbox = TRUE, na = "null")
  }
  invisible(nrow(interactions))
}

browser_ppi_parse_args <- function(values) {
  result <- list()
  i <- 1L
  while (i <= length(values)) {
    key <- values[[i]]
    if (key %in% c("--help", "-h")) {
      result$help <- TRUE
      i <- i + 1L
    } else if (identical(key, "--force")) {
      if (!is.null(result$force)) stop("Repeated --force.", call. = FALSE)
      result$force <- TRUE
      i <- i + 1L
    } else {
      name <- sub("^--", "", key)
      if (!startsWith(key, "--") || !name %in% c("dataset", "annotation-manifest", "output") ||
          !is.null(result[[name]])) stop("Unknown or repeated argument: ", key, call. = FALSE)
      if (i == length(values) || startsWith(values[[i + 1L]], "--")) stop("Missing value for ", key, call. = FALSE)
      result[[name]] <- values[[i + 1L]]
      i <- i + 2L
    }
  }
  result
}

browser_ppi_export_main <- function(values = commandArgs(trailingOnly = TRUE)) {
  args <- browser_ppi_parse_args(values)
  if (isTRUE(args$help)) {
    cat(paste(
      "Usage: Rscript scripts/export_ppi_context.R --dataset ID --annotation-manifest FILE --output DIR [--force]",
      "  Exports only the installed public SpliceImpactR human interaction context.",
      "  FILE is the selected built annotation package's manifest.json.",
      "  DIR receives interactions.ndjson and context_manifest.json for the optional Python importer.",
      "  --force replaces an existing intermediate export, never an annotation package.",
      "  No network requests, isoform PPI predictions, or mouse interaction mapping are performed.", sep = "\n"), "\n")
    return(invisible(NULL))
  }
  required <- c("dataset", "annotation-manifest", "output")
  if (any(!vapply(required, function(key) is.character(args[[key]]) && nzchar(args[[key]]), logical(1)))) {
    stop("--dataset, --annotation-manifest and --output are required. Use --help.", call. = FALSE)
  }
  packages <- c("SpliceImpactR", "jsonlite", "digest")
  missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing)) stop("Missing R packages: ", paste(missing, collapse = ", "),
                           ". Run ./scripts/install_spliceimpactr.sh first.", call. = FALSE)
  script_flag <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  script_path <- normalizePath(sub("^--file=", "", script_flag[[1L]]), mustWork = TRUE)
  root <- dirname(dirname(script_path))
  source(file.path(root, "r", "datasets.R"), local = TRUE)
  registry <- read_browser_dataset_profiles(file.path(root, "backend", "data", "dataset_profiles.json"))
  profile <- browser_dataset_profile(registry, args$dataset)
  annotation_path <- normalizePath(args$`annotation-manifest`, mustWork = TRUE)
  binding <- browser_ppi_annotation_binding(jsonlite::read_json(annotation_path, simplifyVector = FALSE), profile)
  output_dir <- normalizePath(args$output, winslash = "/", mustWork = FALSE)
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  output_file <- file.path(output_dir, "interactions.ndjson")
  receipt_file <- file.path(output_dir, "context_manifest.json")
  if (!isTRUE(args$force) && any(file.exists(c(output_file, receipt_file)))) {
    stop("PPI export already exists. Use another output directory or --force.", call. = FALSE)
  }
  source_file <- system.file("extdata", "ppi.RDS", package = "SpliceImpactR", mustWork = TRUE)
  source_sha256 <- digest::digest(file = source_file, algo = "sha256")
  package_version <- as.character(utils::packageVersion("SpliceImpactR"))
  message("[1/3] Reading installed SpliceImpactR ", package_version, " human interaction context")
  interactions <- SpliceImpactR::get_ppi_interactions()
  browser_ppi_validate_table(interactions)
  # This read is a provenance cross-check only. Exported rows always come
  # from the documented public function, never a custom/private data loader.
  original <- readRDS(source_file)
  if (!is.data.frame(original) || !identical(names(original), names(interactions)) ||
      nrow(original) != nrow(interactions) ||
      !all(vapply(names(interactions), function(field) identical(original[[field]], interactions[[field]]), logical(1))) ||
      !identical(source_sha256, digest::digest(file = source_file, algo = "sha256"))) {
    stop("Public PPI output does not exactly match the recorded bundled data bytes; no export was written.", call. = FALSE)
  }
  rm(original)
  invisible(gc())
  staged_data <- tempfile(".ppi-data-", tmpdir = output_dir)
  staged_receipt <- tempfile(".ppi-receipt-", tmpdir = output_dir)
  on.exit(unlink(c(staged_data, staged_receipt)), add = TRUE)
  message("[2/3] Writing ", nrow(interactions), " context records in bounded chunks")
  browser_ppi_write_ndjson(interactions, staged_data)
  receipt <- c(list(schema = "transcript-browser-ppi-context-export/v1", kind = "gene-level-interaction-context"),
               binding, list(package = "SpliceImpactR", package_version = package_version,
                 source_rds_sha256 = source_sha256, input_file = "interactions.ndjson",
                 input_sha256 = digest::digest(file = staged_data, algo = "sha256"),
                 records = nrow(interactions), unique_genes = length(unique(c(interactions$geneA, interactions$geneB))),
                 network_annotation_release_matched = FALSE,
                 source = "bundled SpliceImpactR BioGRID-backed DDI/DMI context",
                 provenance = list(
                   api = "SpliceImpactR::get_ppi_interactions", source_snapshot = "identified by source_rds_sha256",
                   network_ensembl_release = NULL, network_calendar_release = NULL,
                   endpoint_semantics = "A/B identify gene endpoints, not fixed domain/motif roles; token sets are aggregated independently and original token-to-token pairing is not supplied.",
                   interpretation = "Gene-level interaction context, not isoform gained/lost interactions, probabilities, or a claim that every BioGRID edge is a direct physical interaction.",
                   data_terms = "Bundled scientific data retain upstream resource terms; the browser MIT license does not relicense these generated data.")))
  jsonlite::write_json(receipt, staged_receipt, auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null")
  message("[3/3] Publishing the intermediate export and its checksum-bound receipt")
  if (!file.rename(staged_data, output_file)) stop("Cannot publish PPI NDJSON export.", call. = FALSE)
  # Manifest is published last. An interrupted replacement cannot pass the
  # importer's checksum validation with stale metadata and new data bytes.
  if (!file.rename(staged_receipt, receipt_file)) stop("Cannot publish PPI context receipt.", call. = FALSE)
  message("Exported ", receipt$records, " human gene-context records for ", receipt$dataset_id,
          "; PPI predictions remain disabled.")
  invisible(receipt)
}

if (sys.nframe() == 0L) browser_ppi_export_main()
