# Contributing

Keep the browser local-first and its scientific data separate from user notes
and view state. For development setup, see the [frontend](frontend/README.md)
and [R adapter](r/README.md) guides.

Before opening a pull request:

```bash
./scripts/test_source.sh --require-all
```

Add focused regressions for changed behavior and run the relevant
[API/browser checks](docs/testing.md). Coordinate, translation, source-semantic
or dataset changes need a [critical review](docs/critical_review_addendum.md).
New annotation releases require a verified species/assembly/Ensembl pairing,
input checksums, inventories and a separate scientific build.

Do not commit downloaded annotations, RDS caches, SQLite databases, generated
app bundles, dependencies, logs, credentials or private workspace content.
Review the staged diff; the publication audit is part of the source suite.

Describe what changed and which checks passed. Report browser observations and
biological review separately from automated test results.
