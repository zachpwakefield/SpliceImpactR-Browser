# SpliceImpactR Browser

A local browser for transcript isoforms, protein domains and sequences.
[SpliceImpactR](https://bioconductor.org/packages/release/bioc/html/SpliceImpactR.html)
prepares the annotations; the browser lets you explore them together.
Once setup is complete, you can browse offline.

- See exon, CDS and UTR structure alongside protein features on genomic and
  amino-acid scales.
- Compare isoforms and highlight genomic events across transcripts and proteins.
- Inspect sequences, export PDFs and tables, and keep favorites and notes locally.

![SP1 protein features on genomic and protein coordinates](docs/assets/sp1-expanded-protein-features.jpg)

*SP1 transcript structure with exon-aware protein features.*

## Install

You need [Python](https://www.python.org/downloads/) 3.9–3.14,
[Node.js](https://nodejs.org/en/download) 22.13+ and
[R](https://cran.r-project.org/) 4.6+. Use macOS, Linux or Windows with WSL2.
First setup needs internet access and several GB of disk space; the
genome downloads are more than 3 GB. Linux users: install these
[R build prerequisites](docs/data_preparation.md#system-prerequisites) first.

```bash
git clone https://github.com/zachpwakefield/transcript-browser-shareable.git
cd transcript-browser-shareable
./scripts/setup_local.sh
```

Setup installs the browser dependencies and Bioconductor SpliceImpactR,
downloads human v45 annotations and protein features, builds the local database,
and starts the server. Open the local URL printed in the terminal.
Keep that terminal open; Ctrl+C stops the server. Rerun setup to resume an
interrupted preparation.

No Git? [Download the ZIP](https://github.com/zachpwakefield/transcript-browser-shareable/archive/refs/heads/main.zip),
extract it, open a terminal in that folder, and run `./scripts/setup_local.sh`.
Data is downloaded during setup, not included in the repository. A whole-genome
FASTA and samtools are not needed.

### Human or mouse

| Dataset | Assembly | Ensembl features |
| --- | --- | --- |
| Human GENCODE v45 · default | GRCh38.p14 | 111 |
| Mouse GENCODE M34 | GRCm39 | 111 |

For mouse, use this setup command instead. To add mouse later, stop the running
server first:

```bash
./scripts/setup_local.sh --dataset mouse-gencode-m34
```

Choose among prepared datasets in **Genome annotation**.
Both releases retain every transcript in their source GTF.
Already have annotation files or a SpliceImpactR cache? See
[using existing data](docs/data_preparation.md).

## Use

Start an already prepared browser from the project folder:

```bash
./run_local.sh
```

For mouse, use `./run_local.sh --dataset mouse-gencode-m34`.

1. **Find:** search a gene name, transcript/protein ID, or genomic interval.
2. **Navigate:** drag to pan; use zoom, **Fit gene** or **Fit transcript**.
3. **Show features:** expand a transcript. **View → Default protein tracks → All**
   opens all translated rows; **Top** opens the first, and **None** starts collapsed.
4. **Compare:** choose a second transcript and open **Compare** for shared and
   differing feature calls and amino-acid ranges.
5. **Inspect and save:** use the inspector for sequences and feature details;
   export tables/PDFs or save a session to return later.

InterPro, Pfam, CDD, TMHMM, SignalP, MobiDB-lite and ELM can be toggled separately.
Optional [human PPI context](docs/data_preparation.md#optional-human-ppi-context)
adds recorded interaction partners and feature evidence for each isoform to
**Compare**.

### Event highlights

Search a gene, open **Event highlights**, paste `chrX:1-3,5-9,22-50`, and click
**Add highlights**. Use your actual **1-based inclusive** coordinates.
Marks appear across transcript rows and on protein axes where coding bases map
to residues. **Fit highlights** zooms to the events; remove individual ranges
or clear the list. Highlights are included in saved views and sessions.

For other controls and shortcuts, see the [short user guide](docs/user_guide.md).
For an app icon in your Mac Dock, follow the [Mac launcher instructions](desktop_app/README.md).

## Screenshots

**Isoform comparison:** see the actual feature calls and ranges for two transcripts.

![SP1 isoforms compared by protein-feature accession and amino-acid range](docs/assets/sp1-feature-call-comparison.jpg)

## Help and development

- [Data setup and optional PPI](docs/data_preparation.md)
- [Quick fixes](docs/user_guide.md#quick-fixes) and [current limits](docs/limitations.md)
- [Contributing and testing](CONTRIBUTING.md)

<details>
<summary>Technical reference and project history</summary>

[Architecture](docs/architecture.md) · [Coordinate contract](docs/coordinate_contract.md) ·
[Original implementation plan](docs/LOCAL_TRANSCRIPT_BROWSER_IMPLEMENTATION_PLAN.md) ·
[Validation and review records](docs/README.md)

</details>

## License

Browser code: [MIT License](LICENSE). SpliceImpactR and annotation resources
retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
