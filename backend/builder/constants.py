"""Pinned release, input, feature-source, and reference constants."""

from __future__ import annotations

from collections import OrderedDict

SCHEMA_VERSION = "1.1.0"
BUILDER_VERSION = "0.5.0"

GENCODE_RELEASE = "GENCODE v45"
ENSEMBL_RELEASE = 111
ASSEMBLY = "GRCh38.p14"

REQUIRED_INPUTS = OrderedDict(
    [
        (
            "gencode.v45.annotation.gtf.gz",
            "b6eeb6c9791b7a43a5504a654ff09d9a",
        ),
        (
            "gencode.v45.pc_transcripts.fa.gz",
            "229d2da3b0dc7e83dd8ae69034be1169",
        ),
        (
            "gencode.v45.pc_translations.fa.gz",
            "cf7b19def48b2235abde68df419b4b03",
        ),
    ]
)

FEATURE_SOURCES = OrderedDict(
    [
        ("interpro", "interpro.rds"),
        ("pfam", "pfam.rds"),
        ("cdd", "cdd.rds"),
        ("tmhmm", "tmhmm.rds"),
        ("signalp", "signalp.rds"),
        ("mobidblite", "mobidblite.rds"),
        ("elm", "elm.rds"),
    ]
)

PREPARATION_MANIFEST = "spliceimpactr_manifest.json"
PREPARATION_SCHEMA = "transcript-browser-spliceimpactr-cache/v2"
ANNOTATION_POLICY = {
    "transcript_support_level_filter": None,
    "transcript_biotype_filter": None,
    "exclude_incomplete_cds": False,
}
FEATURE_QUERY_POLICY = {
    "biomart_transcript_biotype_filter": None,
    "provider": "explicit-release-111-archive/public-biomaRt",
    "normalization_api": "SpliceImpactR::get_manual_features",
    "annotation_models_removed": False,
    "test_fixture": False,
    "combine_overlaps": False,
}
FEATURE_COLUMNS = (
    "ensembl_transcript_id", "start", "stop", "chr", "strand",
    "feature_id", "clean_name", "alt_name", "database",
    "ensembl_peptide_id", "method", "name",
)

EXPECTED_GTF_FEATURE_ROWS = OrderedDict(
    [
        ("gene", 63_187),
        ("transcript", 252_930),
        ("exon", 1_650_704),
        ("CDS", 885_749),
        ("UTR", 384_769),
        ("start_codon", 98_063),
        ("stop_codon", 91_945),
        ("Selenocysteine", 130),
    ]
)
EXPECTED_GTF_TOTAL_ROWS = 3_427_477
EXPECTED_PC_TRANSCRIPT_FASTA_RECORDS = 111_048
EXPECTED_PC_TRANSLATION_FASTA_RECORDS = 111_048

# Power-of-four levels keep broad queries small while providing a useful
# overview at intermediate spans. Tiles are complete (zero-count rows included)
# and use the same 0-based half-open convention as every machine coordinate.
DENSITY_TILE_SIZES = (16_384, 65_536, 262_144, 1_048_576)

OFFICIAL_GENCODE_PRIMARY_GENOME_GZ_MD5 = "ad62ff4d71d0b5b8d7feabbec5ce86bf"

# The reference FASTA is intentionally supplied by the caller.  Keeping a
# workstation-specific default here would make generated manifests leak a
# local path and would make a cloned checkout non-reproducible.
REFERENCE_FASTA_SHA256 = (
    "3de3ef4d804e8df197ca66683056d30995756fe60c351449a1629b31d67bb436"
)
REFERENCE_FAI_SHA256 = (
    "f3434563a0fd92a4a65cfeabaf78291e05c2ac6eaccb5e1ade45ea5131dc80de"
)
REFERENCE_PROVENANCE = {
    "provider": "Ensembl",
    "ensembl_release": 115,
    "assembly": ASSEMBLY,
    "sequence_set": "Homo_sapiens.GRCh38.dna.toplevel.fa",
    "note": (
        "Ensembl releases 110 through 116 use GRCh38.p14. Primary chromosome "
        "sequence lengths are identical for the GENCODE v45/Ensembl 111 build."
    ),
}

# GRCh38.p14 primary/reference chromosome lengths. The GENCODE v45 CHR GTF
# contains exactly these 25 sequence regions.
PRIMARY_CONTIG_LENGTHS = OrderedDict(
    [
        ("chr1", 248_956_422),
        ("chr2", 242_193_529),
        ("chr3", 198_295_559),
        ("chr4", 190_214_555),
        ("chr5", 181_538_259),
        ("chr6", 170_805_979),
        ("chr7", 159_345_973),
        ("chr8", 145_138_636),
        ("chr9", 138_394_717),
        ("chr10", 133_797_422),
        ("chr11", 135_086_622),
        ("chr12", 133_275_309),
        ("chr13", 114_364_328),
        ("chr14", 107_043_718),
        ("chr15", 101_991_189),
        ("chr16", 90_338_345),
        ("chr17", 83_257_441),
        ("chr18", 80_373_285),
        ("chr19", 58_617_616),
        ("chr20", 64_444_167),
        ("chr21", 46_709_983),
        ("chr22", 50_818_468),
        ("chrX", 156_040_895),
        ("chrY", 57_227_415),
        ("chrM", 16_569),
    ]
)


def fasta_contig_name(canonical_name: str) -> str:
    """Return the Ensembl FASTA sequence name for a canonical GENCODE name."""

    if canonical_name == "chrM":
        return "MT"
    return canonical_name.removeprefix("chr")
