# Non-interactive first installs must not depend on a writable system library.
ensure_browser_r_library <- function(paths = .libPaths(), user_library = Sys.getenv("R_LIBS_USER")) {
  writable <- paths[dir.exists(paths) & file.access(paths, 2L) == 0L]
  if (length(writable)) {
    library <- writable[[1L]]
  } else {
    candidates <- strsplit(user_library, .Platform$path.sep, fixed = TRUE)[[1L]]
    if (!length(candidates) || !nzchar(candidates[[1L]])) {
      stop("No writable R library. Set R_LIBS_USER to a writable directory and rerun the installer.", call. = FALSE)
    }
    library <- path.expand(candidates[[1L]])
    dir.create(library, recursive = TRUE, showWarnings = FALSE)
    if (!dir.exists(library) || file.access(library, 2L) != 0L) {
      stop("The personal R library is not writable. Set R_LIBS_USER to a writable directory and rerun the installer.", call. = FALSE)
    }
  }
  .libPaths(c(library, paths))
  invisible(library)
}
