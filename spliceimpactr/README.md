# SpliceImpactR dependency

SpliceImpactR is installed from Bioconductor, not included in this repository.
The normal [setup command](../README.md#install) installs it automatically.

For a separately managed R environment, run from the repository root:

```bash
./scripts/install_spliceimpactr.sh
Rscript scripts/prepare_spliceimpactr_cache.R \
  --dataset human-gencode-v45 \
  --output data/cache --base-dir data/spliceimpactr-cache
```

Use `--dataset mouse-gencode-m34` and separate cache directories for mouse.
See [data preparation](../docs/data_preparation.md) for building and launching
the resulting dataset, and [R adapter](../r/README.md) for implementation details.
SpliceImpactR retains its upstream GPL-3 license; see
[third-party notices](../THIRD_PARTY_NOTICES.md).
