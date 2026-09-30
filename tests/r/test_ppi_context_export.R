# Offline public-export contract tests. No network or annotation data needed.
local({
  source("scripts/export_ppi_context.R")
  source("r/datasets.R")
  registry <- read_browser_dataset_profiles("backend/data/dataset_profiles.json")
  human <- browser_dataset_profile(registry, "human-gencode-v45")
  manifest <- list(dataset_id = human$dataset_id, species = "human", gencode_release = 45L,
                   release = "GENCODE v45", ensembl_release = 111L, assembly = "GRCh38.p14",
                   build_hash = paste(rep("a", 64L), collapse = ""))
  fails <- function(expression) stopifnot(inherits(try(force(expression), silent = TRUE), "try-error"))
  binding <- browser_ppi_annotation_binding(manifest, human)
  stopifnot(identical(binding$annotation_build_hash, manifest$build_hash), identical(binding$dataset_id, human$dataset_id))
  legacy <- manifest
  legacy[c("dataset_id", "species", "gencode_release")] <- NULL
  stopifnot(identical(browser_ppi_annotation_binding(legacy, human), binding))
  fails(browser_ppi_annotation_binding(legacy, browser_dataset_profile(registry, "human-gencode-v50")))
  fails(browser_ppi_annotation_binding(manifest, browser_dataset_profile(registry, "mouse-gencode-m39")))
  for (field in c("dataset_id", "species", "gencode_release", "ensembl_release", "assembly", "build_hash")) {
    wrong <- manifest
    wrong[[field]] <- "wrong"
    fails(browser_ppi_annotation_binding(wrong, human))
  }
  wrong <- manifest
  wrong$datasetId <- "human-gencode-v50"
  fails(browser_ppi_annotation_binding(wrong, human))
  wrong <- manifest
  wrong$buildHash <- paste(rep("b", 64L), collapse = "")
  fails(browser_ppi_annotation_binding(wrong, human))

  a <- "ENSG00000000001"
  b <- "ENSG00000000002"
  c <- "ENSG00000000003"
  interactions <- data.frame(geneA = c(a, b, c, a), geneB = c(b, a, c, b),
                             biogrid = rep(TRUE, 4L), DDI = c(TRUE, FALSE, FALSE, TRUE),
                             DMI = c(FALSE, TRUE, FALSE, FALSE), stringsAsFactors = FALSE)
  interactions$DDI_A <- list("PF00001", NULL, character(), "PF00001")
  interactions$DDI_B <- list(c("PF00002", "PF00003"), NULL, character(), c("PF00002", "PF00003"))
  # Canonicalized endpoint lists are mixed; A is not assumed to be domain,
  # B motif. Unsupported identifiers remain honest, unmapped source tokens.
  interactions$DMI_A <- list(NULL, c("DOC_TEST", "SM00028"), character(), NULL)
  interactions$DMI_B <- list(NULL, c("PF00004", "IPR000005"), character(), NULL)
  browser_ppi_validate_table(interactions)
  directory <- tempfile("ppi-export-offline-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  first <- file.path(directory, "one.ndjson")
  second <- file.path(directory, "two.ndjson")
  browser_ppi_write_ndjson(interactions, first, chunk_size = 1L)
  browser_ppi_write_ndjson(interactions, second, chunk_size = 3L)
  stopifnot(identical(digest::digest(file = first, algo = "sha256"), digest::digest(file = second, algo = "sha256")))
  rows <- lapply(readLines(first), jsonlite::fromJSON, simplifyVector = FALSE)
  expected_names <- c("geneA", "geneB", "biogrid", "ddi", "dmi", "ddiA", "ddiB", "dmiA", "dmiB")
  stopifnot(length(rows) == nrow(interactions), all(vapply(rows, function(row) identical(names(row), expected_names), logical(1))),
            identical(rows[[1L]]$ddiA, list("PF00001")), identical(rows[[1L]]$dmiA, list()),
            identical(rows[[2L]]$geneA, b), identical(rows[[2L]]$geneB, a),
            identical(rows[[2L]]$dmiA, list("DOC_TEST", "SM00028")),
            identical(rows[[2L]]$dmiB, list("PF00004", "IPR000005")),
            identical(rows[[3L]]$geneA, rows[[3L]]$geneB), identical(rows[[1L]], rows[[4L]]),
            is.logical(rows[[1L]]$biogrid), is.logical(rows[[1L]]$ddi))

  for (mutate in list(
    function(x) {x$geneA[[1L]] <- "ENSMUSG00000000001"; x},
    function(x) {x$geneB[[1L]] <- paste0(b, ".1"); x},
    function(x) {x$DDI[[1L]] <- NA; x},
    function(x) {x$biogrid <- as.integer(x$biogrid); x},
    function(x) {x$DMI_A[[2L]] <- c("DOC_TEST", NA_character_); x},
    function(x) {x$DDI_A[[1L]] <- 1L; x},
    function(x) {x$DMI_B[[2L]] <- ""; x},
    function(x) {x$DDI[[1L]] <- FALSE; x},
    function(x) {x$DMI[[3L]] <- TRUE; x},
    function(x) {x$unexpected <- 1; x}
  )) fails(browser_ppi_validate_table(mutate(interactions)))
  fails(browser_ppi_write_ndjson(interactions, first, chunk_size = 1.5))
  fails(browser_ppi_parse_args(c("--dataset", "human-gencode-v45", "--dataset", "human-gencode-v50")))
  fails(browser_ppi_parse_args(c("--input-rds", "custom.rds")))
  fails(browser_ppi_parse_args(c("--output")))
  cat("PPI context exporter offline contract tests passed.\n")
})
