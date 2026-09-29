MINIMUM_R_VERSION <- "4.5.0"

assert_supported_r_version <- function(actual = as.character(getRversion())) {
  if (numeric_version(actual) < numeric_version(MINIMUM_R_VERSION)) {
    stop("Unsupported R runtime: need R >= ", MINIMUM_R_VERSION, "; found ", actual,
         ". Use the R 4.6 environment documented in the README.", call. = FALSE)
  }
  actual
}

read_dependency_requirements <- function(path) {
  if (!file.exists(path)) stop("R dependency requirements are missing.", call. = FALSE)
  requirements <- read.delim(path, colClasses = "character", check.names = FALSE)
  if (!identical(names(requirements), c("package", "minimum_version")) ||
      !nrow(requirements) || anyDuplicated(requirements$package) ||
      any(!nzchar(requirements$package)) || any(!nzchar(requirements$minimum_version))) {
    stop("R requirements must contain unique package and minimum_version columns.", call. = FALSE)
  }
  requirements
}

run_dependency_preflight <- function(path) {
  assert_supported_r_version()
  requirements <- read_dependency_requirements(path)
  versions <- setNames(rep(NA_character_, nrow(requirements)), requirements$package)
  problems <- character()
  for (index in seq_len(nrow(requirements))) {
    package <- requirements$package[[index]]
    minimum <- requirements$minimum_version[[index]]
    if (!requireNamespace(package, quietly = TRUE)) {
      problems <- c(problems, paste0(package, ": need >= ", minimum, "; not installed"))
    } else {
      actual <- as.character(utils::packageVersion(package))
      versions[[package]] <- actual
      if (numeric_version(actual) < numeric_version(minimum)) {
        problems <- c(problems, paste0(package, ": need >= ", minimum, "; found ", actual))
      }
    }
  }
  if (length(problems)) {
    stop(paste(c("R dependency preflight failed.", problems,
      "Run ./scripts/install_spliceimpactr.sh to install the preparation/export dependencies."), collapse = "\n"), call. = FALSE)
  }
  versions
}
