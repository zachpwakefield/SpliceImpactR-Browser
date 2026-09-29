# Release-pinned retrieval through public APIs. Ensembl's current website can
# break biomaRt archive discovery even while the historical mart is healthy.
# No private functions, namespace patches, or third-party source are used.
BROWSER_ENSEMBL_HOST <- "https://jan2024.archive.ensembl.org"

browser_mart_chromosomes <- function(chromosomes) {
  names <- sub("^chr", "", chromosomes)
  names[names == "M"] <- "MT"
  sort(unique(names))
}

browser_archive_mart <- function() {
  stopifnot(requireNamespace("biomaRt", quietly = TRUE))
  registry <- httr::GET(paste0(BROWSER_ENSEMBL_HOST, "/biomart/martservice"),
                       query = list(type = "registry"), httr::timeout(120))
  httr::stop_for_status(registry)
  if (!grepl('database="ensembl_mart_111"', httr::content(registry, as = "text", encoding = "UTF-8"), fixed = TRUE)) {
    stop("The pinned archive does not identify Ensembl Genes 111; refusing another release.", call. = FALSE)
  }
  # Mart is a documented S4 class. Constructing a release-specific connection
  # avoids automatic archive-list discovery; useDataset validates metadata.
  mart <- methods::new("Mart", biomart = "ENSEMBL_MART_ENSEMBL", vschema = "default",
    host = paste0(BROWSER_ENSEMBL_HOST, ":443/biomart/martservice?redirect=no"))
  biomaRt::useDataset("hsapiens_gene_ensembl", mart = mart)
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
  start <- raw[[paste0(source, "_start")]]
  stop <- raw[[paste0(source, "_end")]]
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

browser_archive_features <- function(source, annotation, sequences, mart, base_dir,
                                     force = FALSE, query = biomaRt::getBM) {
  chromosomes <- browser_mart_chromosomes(annotation[type == "transcript", chr])
  if (source == "elm") {
    mapping <- query(attributes = c("uniprotswissprot", "ensembl_transcript_id", "ensembl_peptide_id"),
      filters = "chromosome_name", values = chromosomes, mart = mart, useCache = !force)
    # These are the official public HTTP endpoints used by SpliceImpactR 1.0.0.
    # No credentials are sent. Receipts record the actual public download bytes.
    instances <- browser_elm_table("http://elm.eu.org/instances.tsv?q=*&taxon=Homo%20sapiens&instance_logic=true%20positive", base_dir, force)
    classes <- browser_elm_table("http://elm.eu.org/elms/elms_index.tsv", base_dir, force)
    raw <- browser_confirm_elm(instances$table, classes$table, mapping, sequences)
    retrieval <- list(instances = instances$receipt, classes = classes$receipt)
  } else {
    attributes <- browser_feature_attributes(source)
    if (!all(attributes %in% biomaRt::listAttributes(mart)$name)) stop("Pinned archive lacks ", source, " attributes.", call. = FALSE)
    parts <- lapply(chromosomes, function(chromosome) {
      message("    ", source, " chr", chromosome)
      query(attributes = attributes, filters = "chromosome_name", values = chromosome,
            mart = mart, useCache = !force)
    })
    raw <- browser_long_features(data.table::rbindlist(parts), source)
    retrieval <- list(host = BROWSER_ENSEMBL_HOST, release = 111L)
  }
  # Membership is the raw catalog, not TSL, biotype, or completeness criteria.
  raw <- raw[ensembl_transcript_id %in% annotation[type == "transcript", transcript_id]]
  if (!nrow(raw)) {
    output <- normalize_browser_features(data.frame(), source)
  } else {
    output <- SpliceImpactR::get_manual_features(unique(raw), annotation)
    output[, method := if (source == "elm") "elm" else "biomaRt"]
    # Upstream manual-feature bounding names have a negative-strand bug in
    # 1.0.0. Do not present those bounds as evidence. Exact geometry is rebuilt
    # independently from the raw GTF by the Python builder.
    output[, name := clean_name]
  }
  attr(output, "browser_retrieval") <- retrieval
  output
}
