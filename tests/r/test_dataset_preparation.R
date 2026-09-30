# Offline adversarial tests: no remote dependency or genome-scale data needed.
local({
  source("r/datasets.R")
  source("r/browser_annotation.R")
  source("r/archive_features.R")
  registry <- read_browser_dataset_profiles("backend/data/dataset_profiles.json")
  profiles <- registry$profiles
  stopifnot(identical(names(profiles), c("human-gencode-v45", "human-gencode-v50", "mouse-gencode-m39")),
            profiles[[1L]]$gencode_release == 45L, profiles[[1L]]$ensembl_release == 111L,
            profiles[[2L]]$gencode_release == 50L, profiles[[2L]]$ensembl_release == 116L,
            identical(profiles[[3L]]$gencode_release, "M39"), profiles[[3L]]$ensembl_release == 116L,
            identical(profiles[[3L]]$biomart$dataset, "mmusculus_gene_ensembl"))
  fails <- function(expression) stopifnot(inherits(try(force(expression), silent = TRUE), "try-error"))
  fails(browser_dataset_profile(registry, "human-gencode-v999"))
  directory <- tempfile("browser-dataset-tests-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)

  # Profile-consistency checks fail before accession or processing.
  for (mutation in c("ensembl-release", "species")) {
    bad <- jsonlite::read_json("backend/data/dataset_profiles.json", simplifyVector = FALSE)
    if (mutation == "ensembl-release") bad$profiles[[1L]]$ensembl_release <- 116L else bad$profiles[[1L]]$species <- "mouse"
    bad_path <- file.path(directory, paste0(mutation, ".json"))
    jsonlite::write_json(bad, bad_path, auto_unbox = TRUE, null = "null")
    fails(read_browser_dataset_profiles(bad_path))
  }

  fixture_row <- function(profile, type, id, start, end, transcript = NULL, tsl = NULL,
                          biotype = "protein_coding", cds = FALSE, tag = NULL) {
    attrs <- paste0('gene_id "', profile$identifier_prefixes$gene, '00000000001.1";')
    if (!is.null(transcript)) {
      attrs <- paste0(attrs, ' transcript_id "', transcript, '"; transcript_type "', biotype, '";')
    }
    if (type %in% c("exon", "CDS")) attrs <- paste0(attrs, ' exon_number 1; exon_id "', profile$identifier_prefixes$exon, '00000000001.1";')
    if (!is.null(tsl)) attrs <- paste0(attrs, ' transcript_support_level "', tsl, '";')
    if (!is.null(tag)) attrs <- paste0(attrs, ' tag "', tag, '";')
    paste("chr1", "fixture", type, start, end, ".", "+", if (cds) "0" else ".", attrs, sep = "\t")
  }
  for (profile in profiles) {
    # Retain low-supported, missing-TSL, noncoding, incomplete-CDS, no-feature
    # and non-protein-coding models independently of feature availability.
    ids <- paste0(profile$identifier_prefixes$transcript, sprintf("%011d", 1:6), ".1")
    lines <- c(paste0("##description: fixture ", paste(unlist(profile$gtf_header_tokens), collapse = " / ")),
               "##format: gtf", fixture_row(profile, "gene", NULL, 100L, 1000L))
    for (i in seq_along(ids)) {
      tsl <- if (i == 6L) NULL else as.character(i)
      biotype <- if (i == 5L) "lncRNA" else if (i == 6L) "nonsense_mediated_decay" else "protein_coding"
      tag <- if (i == 4L) "cds_start_NF" else NULL
      lines <- c(lines, fixture_row(profile, "transcript", NULL, 100L + i * 20L, 111L + i * 20L, ids[[i]], tsl, biotype, tag = tag),
                 fixture_row(profile, "exon", NULL, 100L + i * 20L, 111L + i * 20L, ids[[i]], tsl, biotype, tag = tag))
      if (i != 5L) lines <- c(lines, fixture_row(profile, "CDS", NULL, 100L + i * 20L, 108L + i * 20L, ids[[i]], tsl, biotype, cds = TRUE, tag = tag))
    }
    path <- file.path(directory, paste0(profile$dataset_id, ".gtf"))
    writeLines(lines, path)
    fixture_profile <- profile
    fixture_profile$expected <- list(gtf_feature_rows = list(gene = 1L, transcript = 6L, exon = 6L, CDS = 5L), gtf_total_rows = 18L)
    fixture_profile$contigs <- list(chr1 = 1000L)
    annotation <- read_browser_annotation(path, fixture_profile)
    stable <- browser_stable_id(ids)
    stopifnot(annotation$inventory$genes == 1L, annotation$inventory$transcripts == 6L,
              setequal(annotation$annotations[type == "transcript", transcript_id], stable),
              annotation$inventory$tsl_counts$unscored == 1L,
              identical(annotation$inventory$transcript_ids_sha256, browser_inventory_sha256(stable)))
    wrong <- fixture_profile
    wrong$gtf_header_tokens <- c("Ensembl 999")
    fails(read_browser_annotation(path, wrong))
    wrong <- fixture_profile
    wrong$identifier_prefixes$transcript <- if (profile$species == "human") "ENSMUST" else "ENST"
    fails(read_browser_annotation(path, wrong))
    wrong <- fixture_profile
    wrong$expected$gtf_feature_rows$transcript <- 7L
    fails(read_browser_annotation(path, wrong))
    fails(browser_verify_raw_asset(path, profile, "gtf"))
    browser_validate_mart_registry(paste0('<MartURLLocation database="', profile$biomart$registry_database, '" />'), profile)
    fails(browser_validate_mart_registry('<MartURLLocation database="ensembl_mart_999" />', profile))
    # Actual archive outages may masquerade as successful HTTP200 responses.
    # HTML is neither an alternate release nor permission to use a fallback.
    for (html in c("<html><head><title>Service unavailable</title></head><body>The Ensembl web service is temporarily unavailable.</body></html>",
                   "<!DOCTYPE HTML><HTML><body>Unexpected status page</body></HTML>")) {
      unavailable <- try(browser_validate_mart_registry(html, profile), silent = TRUE)
      stopifnot(inherits(unavailable, "try-error"),
                grepl("pinned Ensembl archive", as.character(unavailable), fixed = TRUE),
                grepl("temporarily unavailable", as.character(unavailable), fixed = TRUE),
                grepl("Retry later", as.character(unavailable), fixed = TRUE),
                grepl(profile$biomart$host, as.character(unavailable), fixed = TRUE),
                grepl("No fallback was used", as.character(unavailable), fixed = TRUE))
    }
    dataset_meta <- data.frame(dataset = profile$biomart$dataset, version = profile$assembly)
    browser_validate_mart_dataset(dataset_meta, profile)
    dataset_meta$version <- "wrong-assembly"
    fails(browser_validate_mart_dataset(dataset_meta, profile))

    # A valid empty query and unavailable source are different states. Both
    # leave the complete catalog untouched and never add a biotype selector.
    query_count <- 0L
    empty_query <- function(attributes, filters, values, mart, useCache) {
      stopifnot(identical(filters, "chromosome_name"), !any(grepl("biotype", filters)))
      query_count <<- query_count + 1L
      as.data.frame(setNames(rep(list(character()), length(attributes)), attributes))
    }
    empty <- browser_archive_features("pfam", annotation$annotations, NULL, NULL, directory, profile,
      query = empty_query, available_attributes = browser_feature_attributes("pfam"))
    unavailable <- browser_archive_features("cdd", annotation$annotations, NULL, NULL, directory, profile,
      query = function(...) stop("Unavailable source must not be queried"), available_attributes = character())
    stopifnot(query_count == 1L, nrow(empty) == 0L, attr(empty, "browser_retrieval")$status == "available-empty",
              nrow(unavailable) == 0L, attr(unavailable, "browser_retrieval")$status == "unavailable",
              nzchar(attr(unavailable, "browser_retrieval")$reason),
              setequal(annotation$annotations[type == "transcript", transcript_id], stable))
    stopifnot(grepl(if (profile$species == "human") "Homo%20sapiens" else "Mus%20musculus",
                   browser_elm_instances_url(profile), fixed = TRUE))

    # Distinct coincident accessions survive public normalization. Crucially,
    # the 4-7 feature remains 4-7 on a 3-aa CDS, not upstream's clipped 3-3.
    raw_features <- data.frame(ensembl_transcript_id = rep(stable[[1L]], 3L),
      ensembl_peptide_id = paste0(profile$identifier_prefixes$protein, "00000000001"),
      database = "interpro", feature_id = c("IPR-A", "IPR-B", "IPR-OUT"),
      name = c("A", "B", "Outside CDS"), alt_name = c("A", "B", "OUT"),
      start = c(1L, 1L, 4L), stop = c(2L, 2L, 7L))
    normalized <- browser_normalize_raw_features(raw_features, annotation$annotations, "interpro")
    stopifnot(nrow(normalized) == 3L, setequal(normalized$feature_id, raw_features$feature_id),
              normalized$start[normalized$feature_id == "IPR-OUT"] == 4L,
              normalized$stop[normalized$feature_id == "IPR-OUT"] == 7L,
              !any(grepl("browser-source-row", normalized$feature_id, fixed = TRUE)))
    noncoding_feature <- raw_features[1L, ]
    noncoding_feature$ensembl_transcript_id <- stable[[5L]]
    noncoding <- browser_normalize_raw_features(noncoding_feature, annotation$annotations, "interpro")
    stopifnot(nrow(noncoding) == 1L, noncoding$ensembl_transcript_id == stable[[5L]],
              noncoding$start == 1L, noncoding$stop == 2L)
    fails(browser_normalize_raw_features(transform(raw_features, start = 1.5), annotation$annotations, "interpro"))
  }

  # Tiny synthetic raw bytes exercise the public accession/cache contract.
  # Fixture checksums are restricted to this direct helper test; the CLI
  # always loads reviewed official pins from the registry above.
  profile <- profiles[[3L]]
  keys <- c("gtf", "transcripts", "translations")
  input_paths <- setNames(character(length(keys)), keys)
  for (key in keys) {
    input_paths[[key]] <- file.path(directory, paste0("raw-", key))
    writeLines(paste0("synthetic raw ", key), input_paths[[key]])
    profile$raw_inputs[[key]]$md5 <- unname(tools::md5sum(input_paths[[key]]))
  }
  info <- data.frame(rid = keys,
                     fpath = vapply(keys, function(key) browser_raw_asset_url(profile, key), character(1)),
                     rtype = "web", stringsAsFactors = FALSE)
  path_for_rid <- function(rid) input_paths[[rid]]
  found <- browser_cached_raw_asset(info, profile, "gtf", path_for_rid)
  stopifnot(identical(found, normalizePath(input_paths[["gtf"]])))
  wrong_info <- info
  wrong_info$fpath <- sub("Gencode_mouse", "Gencode_human", wrong_info$fpath, fixed = TRUE)
  stopifnot(is.null(browser_cached_raw_asset(wrong_info, profile, "gtf", path_for_rid)))
  wrong_profile <- profile
  wrong_profile$raw_inputs$gtf$md5 <- paste(rep("0", 32L), collapse = "")
  stopifnot(is.null(browser_cached_raw_asset(info, wrong_profile, "gtf", path_for_rid)))
  acquire_count <- 0L
  not_acquired <- function(...) stop("Verified cache reuse must not trigger accession")
  cached <- browser_resolve_raw_assets(profile, file.path(directory, "cache-output"), directory,
    acquire = not_acquired, open_cache = function(path) list(),
    cache_info = function(cache) info, cache_path = function(cache, rid) path_for_rid(rid))
  stopifnot(all(file.exists(cached$paths)), identical(cached$accession$filtered_processed_object_used, FALSE))
  explicit <- browser_resolve_raw_assets(profile, file.path(directory, "explicit-output"), directory,
    explicit = input_paths, acquire = not_acquired,
    open_cache = function(path) stop("Explicit verified raw inputs do not need cache access"))
  stopifnot(all(file.exists(explicit$paths)))
  empty_info <- info[FALSE, ]
  acquire <- function(load, base_dir, species, release, filter_tsl) {
    acquire_count <<- acquire_count + 1L
    stopifnot(identical(load, "link"), identical(species, "mouse"),
              identical(release, "M39"), identical(filter_tsl, as.character(1:5)))
    empty_info <<- info
    # A deliberately filtered catalog must never be used by the browser.
    list(annotations = data.frame(transcript_id = "DROPPED_ALL_OTHER_MODELS"))
  }
  acquired <- browser_resolve_raw_assets(profile, file.path(directory, "acquired-output"), directory,
    acquire = acquire, open_cache = function(path) list(),
    cache_info = function(cache) empty_info, cache_path = function(cache, rid) path_for_rid(rid))
  stopifnot(acquire_count == 1L, all(file.exists(acquired$paths)),
            identical(acquired$accession$filtered_processed_object_used, FALSE))
  # A processing error is tolerated only after every official raw checksum
  # verifies. Failed accession must never produce an apparently valid cache.
  empty_info <- info[FALSE, ]
  acquire_failed_after_raw <- function(...) {
    empty_info <<- info
    stop("Fixture processed annotation failure")
  }
  failed_processing <- browser_resolve_raw_assets(profile, file.path(directory, "processing-failure"), directory,
    acquire = acquire_failed_after_raw, open_cache = function(path) list(),
    cache_info = function(cache) empty_info, cache_path = function(cache, rid) path_for_rid(rid))
  stopifnot(identical(failed_processing$operational$processed_object_status, "failed-after-verified-raw-accession"),
            identical(failed_processing$accession, acquired$accession),
            identical(failed_processing$receipts, acquired$receipts),
            identical(acquired$receipts, explicit$receipts))
  fails(browser_resolve_raw_assets(profile, file.path(directory, "failed-accession"), directory,
    acquire = function(...) stop("Network failure"), open_cache = function(path) list(),
    cache_info = function(cache) info[FALSE, ], cache_path = function(cache, rid) path_for_rid(rid)))
  fails(browser_resolve_raw_assets(profile, file.path(directory, "partial-explicit"), directory,
                                  explicit = c(gtf = input_paths[[1L]], transcripts = NA_character_, translations = NA_character_)))
  cat("Dataset preparation passed: all three release profiles, strict raw identity/cache provenance, public SpliceImpactR accession, complete models, species-aware ELM, source availability, and original feature intervals.\n")
})
