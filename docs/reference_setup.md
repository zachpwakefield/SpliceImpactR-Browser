# Optional whole-genome reference

Skip this for normal transcript, sequence, and protein-feature browsing. It
adds human GRCh38 reference byte-range serving to the local API; mouse reference
serving is not currently supported.

Download [Ensembl's release-115 GRCh38 FASTA](https://ftp.ensembl.org/pub/release-115/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.toplevel.fa.gz)
as `Homo_sapiens.GRCh38.dna.toplevel.fa.gz` and prepare it from the repository root:

```bash
mkdir -p data/reference
gunzip -c Homo_sapiens.GRCh38.dna.toplevel.fa.gz > data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa
samtools faidx data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa
PYTHON=.venv/bin/python ./scripts/build_annotations.sh data/cache \
  --reference-fasta data/reference/Homo_sapiens.GRCh38.dna.toplevel.fa \
  --scope full
```

`samtools` is needed only for this optional indexing step. This is the
checksum-pinned GRCh38.p14 reference adapter; it does not change the browser's
v45/Ensembl-111 annotation or feature release. The builder checks the FASTA and
index against `backend/builder/constants.py`. If a check fails, use the expected
file or rebuild without `--reference-fasta`. Keep these large inputs locally in
`data/reference/`, not in Git.
