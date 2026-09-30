# Release-pinned retrieval through public APIs. Ensembl's current website can
# break biomaRt archive discovery even while the historical mart is healthy.
# No private functions, namespace patches, or third-party source are used.
browser_mart_chromosomes <- function(chromosomes) {
  names <- sub("^chr", "", chromosomes)
  names[names == "M"] <- "MT"
  sort(unique(names))
}

browser_validate_mart_registry <- function(registry_text, profile) {
  # Archive outages can return an HTML status page with HTTP 200. Treat that
  # as service unavailability, not as evidence for a different annotation
  # release. Never substitute a current release or another archive.
  is_html <- grepl("<html([[:space:]]|>)|<!DOCTYPE[[:space:]]+html([[:space:]]|>)",
                   registry_text, ignore.case = TRUE)
  if (is_html) {
    stop("The pinned Ensembl archive for release ", profile$ensembl_release,
         " is temporarily unavailable or returned non-BioMart HTML. Retry later: ",
         profile$biomart$host, ". No fallback was used.", call. = FALSE)
  }
  token <- paste0('database="', profile$biomart$registry_database, '"')
  if (!grepl(token, registry_text, fixed = TRUE)) {
    stop("The pinned archive does not identify Ensembl Genes ", profile$ensembl_release,
         "; refusing another release.", call. = FALSE)
  }
  invisible(TRUE)
}

browser_validate_mart_dataset <- function(datasets, profile) {
  if (!all(c("dataset", "version") %in% names(datasets))) {
    stop("BioMart dataset metadata is incomplete.", call. = FALSE)
  }
  rows <- datasets[datasets$dataset == profile$biomart$dataset, , drop = FALSE]
  if (nrow(rows) != 1L || !identical(as.character(rows$version), profile$assembly)) {
    stop("BioMart species/assembly metadata does not match the selected dataset.", call. = FALSE)
  }
  invisible(TRUE)
}

browser_archive_mart <- function(profile) {
  stopifnot(requireNamespace("biomaRt", quietly = TRUE))
  host <- profile$biomart$host
  registry <- httr::GET(paste0(host, "/biomart/martservice"),
                       query = list(type = "registry"), httr::timeout(120))
  httr::stop_for_status(registry)
  if (!startsWith(registry$url, paste0(host, "/"))) {
    stop("The pinned archive redirected to another host; refusing an unverified fallback.", call. = FALSE)
  }
  browser_validate_mart_registry(httr::content(registry, as = "text", encoding = "UTF-8"), profile)
  # Mart is a documented S4 class. Constructing a release-specific connection
  # avoids automatic archive-list discovery; useDataset validates metadata.
  mart <- methods::new("Mart", biomart = "ENSEMBL_MART_ENSEMBL", vschema = "default",
    host = paste0(host, ":443/biomart/martservice?redirect=no"))
  browser_validate_mart_dataset(biomaRt::listDatasets(mart), profile)
  biomaRt::useDataset(profile$biomart$dataset, mart = mart)
}

browser_feature_attributes <- function(source) {
  if (!source %in% c("interpro", "pfam", "cdd", "tmhmm", "signalp", "mobidblite")) {
    stop("Unknown BioMart source: ", source, call. = FALSE)
  }
  c("ensembl_transcript_id", "ensembl_peptide_id", source,
    if (source == "interpro") c("interpro_short_description", "interpro_description"),
    paste0(source, c("_start", "_end")))
}

browser_long_features <- function(raw, source) {
  if (!all(browser_feature_attributes(source) %in% names(raw))) stop("Incomplete BioMart feature columns.", call. = FALSE)
  raw <- data.table::as.data.table(raw)
  present <- !is.na(raw[[source]]) & nzchar(as.character(raw[[source]]))
  raw <- raw[present]
  start <- suppressWarnings(as.numeric(raw[[paste0(source, "_start")]]))
  stop <- suppressWarnings(as.numeric(raw[[paste0(source, "_end")]]))
  if (anyNA(start) || anyNA(stop) || any(start < 1 | stop < start | start != floor(start) | stop != floor(stop))) {
    stop("Invalid non-empty ", source, " feature coordinates returned by BioMart.", call. = FALSE)
  }
  data.table::data.table(
    ensembl_transcript_id = raw$ensembl_transcript_id,
    ensembl_peptide_id = raw$ensembl_peptide_id,
    database = source, feature_id = as.character(raw[[source]]),
    name = if (source == "interpro") raw$interpro_description else as.character(raw[[source]]),
    alt_name = if (source == "interpro") raw$interpro_short_description else as.character(raw[[source]]),
    start = as.integer(start), stop = as.integer(stop)
  )
}

browser_confirm_elm <- function(instances, classes, mapping, sequences) {
  required <- list(instances = c("Primary_Acc", "ELMIdentifier", "Start", "End"),
                   classes = c("ELMIdentifier", "Regex"),
                   mapping = c("uniprotswissprot", "ensembl_transcript_id", "ensembl_peptide_id"))
  for (kind in names(required)) {
    if (!all(required[[kind]] %in% names(get(kind)))) stop("Invalid ELM ", kind, " columns.", call. = FALSE)
  }
  instances <- data.table::as.data.table(instances)
  classes <- data.table::as.data.table(classes)
  mapping <- data.table::as.data.table(mapping)
  instances <- instances[, .(uniprotswissprot = Primary_Acc, ELMIdentifier, start = Start, stop = End)]
  candidates <- merge(instances, mapping[nzchar(uniprotswissprot)], by = "uniprotswissprot", allow.cartesian = TRUE)
  candidates <- merge(candidates, classes[, .(ELMIdentifier, Regex)], by = "ELMIdentifier", allow.cartesian = TRUE)
  proteins <- sequences[, .(ensembl_peptide_id = protein_id, protein_seq)]
  candidates <- merge(candidates, proteins, by = "ensembl_peptide_id", allow.cartesian = TRUE)
  if (anyNA(candidates$start) || anyNA(candidates$stop) || any(candidates$start < 1 | candidates$stop < candidates$start |
      candidates$start != floor(candidates$start) | candidates$stop != floor(candidates$stop))) {
    stop("Invalid ELM instance coordinates.", call. = FALSE)
  }
  candidates <- candidates[stop <= nchar(protein_seq)]
  confirmed <- mapply(function(regex, sequence, start, stop) {
    if (is.na(regex) || !nzchar(regex)) return(FALSE)
    grepl(regex, substr(sequence, start, stop))
  }, candidates$Regex, candidates$protein_seq, candidates$start, candidates$stop)
  candidates[as.logical(confirmed), .(ensembl_transcript_id, ensembl_peptide_id,
    database = "elm", feature_id = ELMIdentifier, name = ELMIdentifier,
    alt_name = ELMIdentifier, start = as.integer(start), stop = as.integer(stop))]
}

browser_elm_table <- function(url, base_dir, force = FALSE) {
  bfc <- BiocFileCache::BiocFileCache(file.path(base_dir, "elm-downloads"), ask = FALSE)
  hits <- BiocFileCache::bfcquery(bfc, url, field = "rname", exact = TRUE)
  if (!nrow(hits)) {
    path <- unname(BiocFileCache::bfcadd(bfc, rname = url, fpath = url, rtype = "web")[[1L]])
  } else {
    if (nrow(hits) != 1L) stop("Ambiguous ELM cache entry.", call. = FALSE)
    path <- unname(BiocFileCache::bfcpath(bfc, hits$rid))
    if (force || !file.exists(path)) BiocFileCache::bfcdownload(bfc, hits$rid, ask = FALSE)
  }
  table <- data.table::fread(path, skip = 5L, showProgress = FALSE)
  list(table = table, receipt = list(url = url, sha256 = digest::digest(file = path, algo = "sha256")))
}

browser_elm_instances_url <- function(profile) {
  taxon <- if (profile$species == "human") "Homo%20sapiens" else "Mus%20musculus"
  paste0("http://elm.eu.org/instances.tsv?q=*&taxon=", taxon, "&instance_logic=true%20positive")
}

browser_normalize_raw_features <- function(raw, annotation, source) {
  raw <- unique(data.table::as.data.table(raw))
  models <- annotation[type == "transcript", .(ensembl_transcript_id = transcript_id, chr, strand)]
  raw <- raw[ensembl_transcript_id %in% models$ensembl_transcript_id]
  if (!nrow(raw)) return(normalize_browser_features(data.frame(), source))
  required <- c("ensembl_transcript_id", "ensembl_peptide_id", "database", "feature_id", "name", "alt_name", "start", "stop")
  if (!all(required %in% names(raw))) stop("Incomplete source protein-feature table.", call. = FALSE)
  if (anyNA(raw$start) || anyNA(raw$stop) ||
      any(raw$start < 1 | raw$stop < raw$start | raw$start != floor(raw$start) | raw$stop != floor(raw$stop))) {
    stop("Invalid source amino-acid coordinates.", call. = FALSE)
  }
  # get_manual_features() is the released public annotation API. Its 1.0.0
  # implementation clips coordinates to incomplete CDS and groups by the
  # clipped interval. Temporary row keys prevent loss during normalization;
  # every original accession and interval is then restored. Upstream bounding
  # names are never used as genomic geometry by this browser.
  inputs <- data.table::copy(raw)
  row_keys <- paste0("browser-source-row-", seq_len(nrow(inputs)))
  inputs[, feature_id := row_keys]
  raw[, browser_row_key := row_keys]
  coding_ids <- unique(annotation[type == "exon" & cds_has == TRUE, transcript_id])
  processed <- if (any(inputs$ensembl_transcript_id %in% coding_ids)) {
    SpliceImpactR::get_manual_features(inputs[ensembl_transcript_id %in% coding_ids], annotation)
  } else data.table::data.table()
  complete <- merge(raw, models, by = "ensembl_transcript_id", all.x = TRUE, sort = FALSE)
  if (nrow(complete) != nrow(raw) || anyNA(complete$chr) || anyNA(complete$strand)) {
    stop("Raw feature membership must map to exactly one source transcript.", call. = FALSE)
  }
  complete[, `:=`(clean_name = name, method = if (source == "elm") "elm" else "biomaRt")]
  if (nrow(processed)) {
    index <- match(processed$feature_id, row_keys)
    if (anyNA(index) || anyDuplicated(index)) stop("Public feature normalization lost row identity.", call. = FALSE)
    # Compare metadata only; no upstream clipping or bounding coordinate may
    # alter the independently validated source amino-acid interval.
    if (any(processed$ensembl_transcript_id != raw$ensembl_transcript_id[index])) {
      stop("Public feature normalization changed transcript identity.", call. = FALSE)
    }
    rows <- match(processed$feature_id, complete$browser_row_key)
    if (anyNA(rows) || any(processed$chr != complete$chr[rows]) ||
        any(processed$strand != complete$strand[rows])) {
      stop("Public feature normalization changed source locus metadata.", call. = FALSE)
    }
    complete$clean_name[rows] <- processed$clean_name
    complete$alt_name[rows] <- processed$alt_name
  }
  complete[, name := clean_name]
  normalize_browser_features(complete, source)
}

browser_archive_features <- function(source, annotation, sequences, mart, base_dir, profile,
                                     force = FALSE, query = biomaRt::getBM,
                                     available_attributes = biomaRt::listAttributes(mart)$name,
                                     elm_table = browser_elm_table) {
  chromosomes <- browser_mart_chromosomes(annotation[type == "transcript", chr])
  retrieval <- list(host = profile$biomart$host, release = profile$ensembl_release,
                    species = profile$species, dataset = profile$biomart$dataset,
                    status = "available", source_coordinates_preserved = TRUE)
  attributes <- if (source == "elm") c("uniprotswissprot", "ensembl_transcript_id", "ensembl_peptide_id") else browser_feature_attributes(source)
  missing <- setdiff(attributes, available_attributes)
  if (length(missing)) {
    output <- normalize_browser_features(data.frame(), source)
    retrieval$status <- "unavailable"
    retrieval$reason <- paste0("Pinned release/species mart lacks attributes: ", paste(missing, collapse = ", "))
    attr(output, "browser_retrieval") <- retrieval
    return(output)
  }
  if (source == "elm") {
    mapping <- query(attributes = c("uniprotswissprot", "ensembl_transcript_id", "ensembl_peptide_id"),
      filters = "chromosome_name", values = chromosomes, mart = mart, useCache = !force)
    # These are the official public HTTP endpoints used by SpliceImpactR 1.0.0.
    # No credentials are sent. Receipts record the actual public download bytes.
    instances <- elm_table(browser_elm_instances_url(profile), base_dir, force)
    classes <- elm_table("http://elm.eu.org/elms/elms_index.tsv", base_dir, force)
    raw <- browser_confirm_elm(instances$table, classes$table, mapping, sequences)
    retrieval$instances <- instances$receipt
    retrieval$classes <- classes$receipt
    retrieval$taxon <- profile$scientific_name
  } else {
    parts <- lapply(chromosomes, function(chromosome) {
      message("    ", source, " chr", chromosome)
      query(attributes = attributes, filters = "chromosome_name", values = chromosome,
            mart = mart, useCache = !force)
    })
    raw <- browser_long_features(data.table::rbindlist(parts), source)
  }
  # Membership is the raw catalog, not TSL, biotype, or completeness criteria.
  retrieval$raw_source_rows <- nrow(raw)
  raw <- raw[ensembl_transcript_id %in% annotation[type == "transcript", transcript_id]]
  retrieval$retained_catalog_rows <- nrow(raw)
  output <- browser_normalize_raw_features(raw, annotation, source)
  retrieval$normalized_rows <- nrow(output)
  retrieval$status <- if (nrow(output)) "available" else "available-empty"
  attr(output, "browser_retrieval") <- retrieval
  output
}
