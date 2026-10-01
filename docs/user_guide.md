# User guide

## Start the full local browser

To reopen human v45 after [setup](../README.md#install):

```bash
./run_local.sh --open
```

To reopen mouse M34, including a mouse-only installation:

```bash
./run_local.sh --dataset mouse-gencode-m34 --open
```

On macOS, double-click **SpliceImpactR Browser.app** or its Dock icon.

**Genome annotation** switches between prepared datasets. Without `--dataset`, the Terminal launcher defaults to human v45.

## Find and navigate annotations

Search for a gene symbol (`SP1`), transcript name (`SP1-201`), Ensembl gene/transcript/protein/exon ID, or genomic interval (`chr12:53380176-53416446`). Choose a result or press Enter.

Detailed transcript rows show one selected gene. The overview shows neighboring genes; click one to switch. Coordinate search moves the viewport while keeping your selected gene.

- **Fit gene** / **Fit transcript** returns to the complete gene or selected isoform.
- Drag the canvas to pan; use **+ / −**, double-click, or Ctrl/Cmd-wheel to zoom.
- Drag across the ruler to zoom to an interval.
- Scroll vertically through transcripts; the minimap provides a quick jump.
- **Find current transcript**, its dropdown, and **Previous / Next** navigate the current gene’s isoforms. Use **Show more** if offered for a large gene.

## Inspect transcripts and proteins

Click a transcript row to inspect its structure, identifiers, support, and flags. Open the triangle beside its name to reveal protein features.

In **View → Default protein tracks**, choose **All translated transcripts**, **Top translated transcript**, or **None**. Top means the first translated transcript in the gene's default order. Selecting a row alone does not expand it.

Expanded rows pair genomic feature projections with an independent N-to-C protein axis. Hover a feature to connect its protein and exon positions; click for details.

Use source buttons and **Prediction class** to filter features, **Transcripts** to filter isoforms, and **View** for row density. Pin useful transcripts or use **↕ Reorder** to place rows together.

## Highlight genomic events

1. Search for a gene and open **Event highlights**.
2. Paste an interval or a list, then choose **Add highlights**:

   ```text
   chr12:53380176-53380178,53380190-53380205,53380220-53380250
   ```
3. Expand protein tracks to see projections across isoforms.

Coordinates are **1-based inclusive**. The chromosome carries forward through comma-separated ranges; bare ranges use the gene’s chromosome. Start a new line for another chromosome. Thousands separators require one complete interval per line, such as `chr12:53,380,176-53,380,178`.

Colored bands mark genomic intervals and their exon intersections. The panel lists spliced-transcript positions and touched protein residues for the selected and comparison transcripts. Protein positions require an exact coding map; intronic and UTR bases have none. These marks show overlap, not a predicted biological effect.

**Add highlights** keeps your current view. **Fit highlights** fits events on the gene’s chromosome; a coordinate chip jumps to one event. Remove individual events with **×**, or choose **Clear highlights**.

## Compare isoforms

Select one transcript, choose a second with **Comparison transcript**, then open **Compare**.

**Actual protein-feature differences** shows calls unique to either isoform, changed call counts, and different amino-acid intervals. Turn off **Show differences only** to include shared calls. Search by feature name/accession, or click an amino-acid range for details.

For prepared human datasets, **PPI context and focal feature evidence** shows recorded gene partners and whether their linked domain/motif identifiers occur in each isoform. This is gene-level context, not an isoform interaction prediction.

## Preserve and export a view

**Workspace** provides recents and favorites. Add notes/tags in the **Gene** or **Transcript** inspector. Saved work stays in your browser, separately for each annotation build.

- **Copy view** copies a URL for the same installation.
- **Export session / Import session** transfers views, highlights, and notes between installations with the same annotation build.
- **Sequence** displays and copies transcript, CDS, or protein sequence.
- **Export JSON / TSV** downloads gene, transcript, or feature data; **Locus JSON / TSV** exports the viewed region.
- Comparison exports provide transcript tables or **Feature calls CSV / TSV**.
- **Save PDF** reports chosen transcripts, structures, features, and sequence excerpts. **Quick PDF** reuses report settings.

## Useful shortcuts

Shortcuts apply outside text fields; canvas controls require canvas focus.

| Control | Action |
| --- | --- |
| `/` | Focus search |
| `J` / `K` | Next / previous transcript |
| `P` | Pin / unpin selected transcript |
| `C` | Open comparison |
| `←` / `→`, `+` / `−` | Pan / zoom canvas |
| Page Up / Down, Home / End | Navigate transcript rows |

## Quick fixes

**Only one protein track?** Choose **View → Default protein tracks → All translated transcripts**.

**Lost the gene while panning?** Choose **Fit gene**.

**Startup failed?** Use the command above matching your prepared dataset, then check the printed error and [setup instructions](../README.md#install). **About & diagnostics → Copy diagnostics** supplies a useful support summary.
