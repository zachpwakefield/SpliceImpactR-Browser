# Genome datasets

The browser supports the corresponding human and mouse annotations from
Ensembl 111:

| Dataset ID | GENCODE | Assembly | Prepared cache | Built database folder |
| --- | --- | --- | --- | --- |
| `human-gencode-v45` | v45 | GRCh38.p14 | `data/cache` | `data/builds/gencode_v45` |
| `mouse-gencode-m34` | M34 | GRCm39 | `data/cache/mouse_gencode_m34` | `data/builds/mouse_gencode_m34` |

## Install and select

From the repository root, run the setup commands for the datasets you need:

```bash
./scripts/setup_local.sh --dataset human-gencode-v45 --no-start
./scripts/setup_local.sh --dataset mouse-gencode-m34 --no-start
./run_local.sh
```

Human v45 opens by default. Choose another installed dataset in **Genome
annotation**, or start directly with
`./run_local.sh --dataset mouse-gencode-m34`. Restart the server after installing
an additional dataset. The selector switches local data without downloading it;
notes and saved views stay associated with their dataset and build.

For custom locations, use `--cache DIR` and `--query-cache DIR` with setup.
[Data preparation](data_preparation.md) explains how to supply existing raw files.
Each profile keeps every source transcript, regardless of TSL, biotype, or
protein-feature coverage. Human PPI context is optional; it is not applied to
mouse.

## Release matching

SpliceImpactR uses GENCODE numbering for annotation accession: human `45` or
mouse `"M34"`. Protein-feature queries use the corresponding Ensembl release
`111`. The browser checks the raw files, species, assembly, and matching feature
archive using `backend/data/dataset_profiles.json`.

Other presets in that registry are experimental, not the recommended setup.
Adding another release requires a new verified profile and build; changing a
dataset label does not convert an existing database. Optional whole-genome
reference serving currently supports human GRCh38 only.
