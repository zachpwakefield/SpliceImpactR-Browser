# Dataset identities and release pairings come from the same reviewed registry
# used by the Python builder. GENCODE releases are not Ensembl release numbers.

read_browser_dataset_profiles <- function(path) {
  registry <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!identical(registry$schema, "transcript-browser-dataset-profiles/v1") ||
      !is.list(registry$profiles) || !length(registry$profiles)) {
    stop("Invalid browser dataset-profile registry.", call. = FALSE)
  }
  identifiers <- vapply(registry$profiles, function(profile) profile$dataset_id, character(1))
  if (anyDuplicated(identifiers) || !registry$default_dataset_id %in% identifiers) {
    stop("Dataset profiles must have unique IDs and a known default.", call. = FALSE)
  }
  names(registry$profiles) <- identifiers
  for (profile in registry$profiles) {
    if (!profile$species %in% c("human", "mouse") ||
        !is.numeric(profile$ensembl_release) || length(profile$ensembl_release) != 1L ||
        profile$ensembl_release < 1 || profile$ensembl_release != floor(profile$ensembl_release)) {
      stop("Invalid species or Ensembl release in dataset profile.", call. = FALSE)
    }
    release <- as.character(profile$gencode_release)
    if (!grepl(if (profile$species == "human") "^[0-9]+$" else "^M[0-9]+$", release)) {
      stop("GENCODE release syntax does not match the dataset species.", call. = FALSE)
    }
    expected_dataset <- if (profile$species == "human") "hsapiens_gene_ensembl" else "mmusculus_gene_ensembl"
    if (!identical(profile$biomart$dataset, expected_dataset) ||
        !identical(profile$biomart$registry_database, paste0("ensembl_mart_", profile$ensembl_release)) ||
        !grepl("^https://[a-z]{3}[0-9]{4}\\.archive\\.ensembl\\.org$", profile$biomart$host)) {
      stop("Dataset BioMart identity must pin the matching species and release archive.", call. = FALSE)
    }
    base <- paste0("https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_", profile$species,
                   "/release_", release)
    if (!identical(profile$raw_base_url, base) ||
        !setequal(names(profile$raw_inputs), c("gtf", "transcripts", "translations"))) {
      stop("Dataset raw inputs must use the matching official GENCODE source.", call. = FALSE)
    }
    suffixes <- c(gtf = "annotation.gtf.gz", transcripts = "pc_transcripts.fa.gz", translations = "pc_translations.fa.gz")
    for (key in names(suffixes)) {
      asset <- profile$raw_inputs[[key]]
      if (!identical(asset$file, paste0("gencode.v", release, ".", suffixes[[key]])) ||
          !is.character(asset$md5) || !grepl("^[0-9a-f]{32}$", asset$md5)) {
        stop("Dataset raw filename/checksum does not match its GENCODE release.", call. = FALSE)
      }
    }
  }
  registry
}

browser_dataset_profile <- function(registry, dataset_id = registry$default_dataset_id) {
  if (!is.character(dataset_id) || length(dataset_id) != 1L ||
      !dataset_id %in% names(registry$profiles)) {
    stop("Unknown dataset ID. Choose one of: ", paste(names(registry$profiles), collapse = ", "), call. = FALSE)
  }
  registry$profiles[[dataset_id]]
}

browser_raw_asset_url <- function(profile, key) {
  paste0(sub("/$", "", profile$raw_base_url), "/", profile$raw_inputs[[key]]$file)
}

browser_verify_raw_asset <- function(path, profile, key) {
  asset <- profile$raw_inputs[[key]]
  if (!is.character(path) || length(path) != 1L || !file.exists(path) || dir.exists(path)) {
    stop("Missing raw GENCODE input: ", asset$file, call. = FALSE)
  }
  actual <- unname(tools::md5sum(path))
  if (!identical(actual, asset$md5)) {
    stop("Wrong GENCODE bytes for ", profile$dataset_id, " / ", asset$file,
         ": expected MD5 ", asset$md5, "; found ", actual, call. = FALSE)
  }
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

browser_validate_gtf_header <- function(path, profile) {
  connection <- gzfile(path, open = "rt")
  on.exit(close(connection), add = TRUE)
  lines <- readLines(connection, n = 30L, warn = FALSE)
  header <- paste(lines[startsWith(lines, "#")], collapse = "\n")
  tokens <- unlist(profile$gtf_header_tokens, use.names = FALSE)
  if (!length(tokens) || any(!vapply(tokens, grepl, logical(1), x = header, fixed = TRUE))) {
    stop("Raw GTF header does not identify the selected assembly, GENCODE, and Ensembl release.", call. = FALSE)
  }
  invisible(TRUE)
}

# Public BiocFileCache metadata is the only bridge to SpliceImpactR's raw
# downloads. Never depend on its private filenames, cache keys, or helpers.
browser_cached_raw_asset <- function(info, profile, key, path_for_rid, verify = browser_verify_raw_asset) {
  if (!nrow(info)) return(NULL)
  required <- c("rid", "fpath", "rtype")
  if (!all(required %in% names(info))) stop("Invalid BiocFileCache asset metadata.", call. = FALSE)
  expected <- browser_raw_asset_url(profile, key)
  matches <- info[!is.na(info$rid) & !is.na(info$fpath) & !is.na(info$rtype) &
                  info$fpath == expected & info$rtype == "web", , drop = FALSE]
  if (!nrow(matches)) return(NULL)
  verified <- character()
  for (rid in matches$rid) {
    path <- unname(path_for_rid(rid))
    if (length(path) == 1L && file.exists(path)) {
      good <- tryCatch(verify(path, profile, key), error = function(e) NULL)
      if (!is.null(good)) verified <- c(verified, good)
    }
  }
  if (!length(verified)) return(NULL)
  # Several verified entries are byte-identical by the official checksum.
  sort(unique(verified), method = "radix")[[1L]]
}

browser_resolve_raw_assets <- function(profile, output_dir, base_dir, explicit = NULL,
                                       acquire = SpliceImpactR::get_annotation,
                                       open_cache = function(path) BiocFileCache::BiocFileCache(path, ask = FALSE),
                                       cache_info = BiocFileCache::bfcinfo,
                                       cache_path = BiocFileCache::bfcpath) {
  keys <- c("gtf", "transcripts", "translations")
  if (is.null(explicit)) explicit <- setNames(rep(NA_character_, length(keys)), keys)
  if (!identical(names(explicit), keys) || (anyNA(explicit) && !all(is.na(explicit)))) {
    stop("Provide all three raw GTF/transcript/protein inputs, or none.", call. = FALSE)
  }
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  dir.create(base_dir, recursive = TRUE, showWarnings = FALSE)
  cache <- NULL
  paths <- setNames(rep(NA_character_, length(keys)), keys)
  acquisition <- setNames(rep("verified-output", length(keys)), keys)
  for (key in keys) {
    destination <- file.path(output_dir, profile$raw_inputs[[key]]$file)
    if (!is.na(explicit[[key]])) {
      paths[[key]] <- browser_verify_raw_asset(explicit[[key]], profile, key)
      acquisition[[key]] <- "explicit-verified-raw"
    } else if (file.exists(destination)) {
      paths[[key]] <- tryCatch(browser_verify_raw_asset(destination, profile, key), error = function(e) NA_character_)
    }
  }
  missing <- keys[is.na(paths)]
  if (length(missing)) {
    cache <- open_cache(file.path(base_dir, "BiocFileCache"))
    info <- cache_info(cache)
    for (key in missing) {
      path <- browser_cached_raw_asset(info, profile, key, function(rid) cache_path(cache, rid))
      if (!is.null(path)) {
        paths[[key]] <- path
        acquisition[[key]] <- "verified-BiocFileCache-raw"
      }
    }
  }
  acquisition_error <- NULL
  if (anyNA(paths)) {
    message("  [SpliceImpactR accession] ", profile$species, " GENCODE ", profile$gencode_release,
            "; its filtered processed object is not used by the browser")
    # No exposed raw-download-only API exists in released SpliceImpactR.
    # get_annotation acquires the raw assets before processing. A processing
    # failure may be tolerated ONLY when all official raw bytes verify below.
    tryCatch({
      discard <- acquire(load = "link", base_dir = base_dir, species = profile$species,
                         release = profile$gencode_release, filter_tsl = as.character(1:5))
      rm(discard)
    }, error = function(e) acquisition_error <<- conditionMessage(e))
    info <- cache_info(cache)
    for (key in keys[is.na(paths)]) {
      path <- browser_cached_raw_asset(info, profile, key, function(rid) cache_path(cache, rid))
      if (!is.null(path)) {
        paths[[key]] <- path
        acquisition[[key]] <- "SpliceImpactR::get_annotation/link-raw"
      }
    }
    if (anyNA(paths)) {
      stop("SpliceImpactR did not provide all verified raw assets for ", profile$dataset_id,
           ". Supply all three matching official files with --gtf, --transcript-fa, --protein-fa.",
           if (!is.null(acquisition_error)) paste0("\nUpstream error: ", acquisition_error) else "", call. = FALSE)
    }
    if (!is.null(acquisition_error)) {
      message("  Upstream processed-object creation failed; every raw checksum is verified, so unfiltered preparation can continue.")
    }
    invisible(gc())
  }
  receipts <- list()
  for (key in keys) {
    asset <- profile$raw_inputs[[key]]
    input <- browser_verify_raw_asset(paths[[key]], profile, key)
    destination <- file.path(output_dir, asset$file)
    if (!identical(input, normalizePath(destination, winslash = "/", mustWork = FALSE))) {
      if (!file.copy(input, destination, overwrite = TRUE)) stop("Cannot copy verified ", asset$file, call. = FALSE)
    }
    # Verify the published copy, not only the cache input.
    browser_verify_raw_asset(destination, profile, key)
    receipts[[asset$file]] <- list(file = asset$file, md5 = asset$md5,
      size = unname(file.info(destination)$size), url = browser_raw_asset_url(profile, key))
    paths[[key]] <- normalizePath(destination, winslash = "/", mustWork = TRUE)
  }
  # Canonical receipts describe source bytes and fixed policy, not whether this
  # particular run reused files or downloaded them. Otherwise the next run
  # would invalidate its own feature cache and alter deterministic build IDs.
  list(paths = paths, receipts = receipts,
       accession = list(api = "SpliceImpactR::get_annotation", filtered_processed_object_used = FALSE,
                        policy = "verified-output-or-explicit-or-BiocFileCache-before-public-link-accession"),
       operational = list(routes = acquisition,
                          processed_object_status = if (is.null(acquisition_error)) "not-required-or-completed" else "failed-after-verified-raw-accession"))
}
