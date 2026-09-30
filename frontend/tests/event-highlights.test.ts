import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { EventHighlights } from "../src/components/EventHighlights.tsx";
import { DEFAULT_VIEW_STATE, SP1_GENE } from "../src/data/sp1.ts";
import {
  checkHighlightBounds, highlightColor, highlightKey, MAX_EVENT_HIGHLIGHTS,
  parseHighlightInput, projectGenomicEvent, validateHighlights,
} from "../src/lib/eventHighlights.ts";
import { encodeSession, parsePortableSession } from "../src/lib/session.ts";
import { encodeViewState, hasExplicitViewState, parseViewState, restoreViewState } from "../src/lib/urlState.ts";
import { createEmptyWorkspaceState, parseWorkspaceState, serializeWorkspaceState } from "../src/lib/workspaceStore.ts";
import type { Gene, Locus, Transcript } from "../src/types.ts";

const chr = "chrX";
const locus = (start0: number, end0: number, chrom = chr): Locus => ({ chrom, start0, end0 });

function transcript(strand: "+" | "-" = "+", firstCodingLength = 5): Transcript {
  const exons = strand === "+"
    ? [{ id: "E1", rank: 1, start0: 100, end0: 110 }, { id: "E2", rank: 2, start0: 200, end0: 220 }]
    : [{ id: "E1", rank: 1, start0: 200, end0: 210 }, { id: "E2", rank: 2, start0: 100, end0: 120 }];
  const codingSegments = strand === "+"
    ? [{ exonRank: 1, start0: 110 - firstCodingLength, end0: 110, codingStart0: 0, codingEnd0: firstCodingLength },
      { exonRank: 2, start0: 200, end0: 218 - firstCodingLength, codingStart0: firstCodingLength, codingEnd0: 18 }]
    : [{ exonRank: 1, start0: 200, end0: 200 + firstCodingLength, codingStart0: 0, codingEnd0: firstCodingLength },
      { exonRank: 2, start0: 102 + firstCodingLength, end0: 120, codingStart0: firstCodingLength, codingEnd0: 18 }];
  return {
    id: `TX_${strand}_${firstCodingLength}`, versionedId: "TX.1", name: "TEST-201", geneId: "G",
    proteinId: "P", versionedProteinId: "P.1", biotype: "protein_coding", start0: 100,
    end0: strand === "+" ? 220 : 210, strand, transcriptLength: 30, cdsLength: 18, proteinLength: 6,
    tsl: "1", tags: [], badges: [], features: [], exons, detailState: "ready",
    translationMapping: { status: "exact", reason: "Verified", cdsStart0: 10 - firstCodingLength, cdsEnd0: 28 - firstCodingLength },
    codingSegments,
  };
}

test("interval input accepts inherited chromosome lists, independent chromosomes and 1-based inclusive single bases", () => {
  assert.deepEqual(parseHighlightInput("chrX:1-3,5-9,22-50"), [locus(0, 3), locus(4, 9), locus(21, 50)]);
  assert.deepEqual(parseHighlightInput("1-1, 5..9", "chrX"), [locus(0, 1), locus(4, 9)]);
  assert.deepEqual(parseHighlightInput("X:10-20;chr2:30-35\nMT:1-3"), [locus(9, 20), locus(29, 35, "chr2"), locus(0, 3, "chrM")]);
  assert.deepEqual(parseHighlightInput("chrX:77,910,739-77,910,741\nchrX:78,000,000-78,000,003"), [locus(77910738, 77910741), locus(77999999, 78000003)]);
});

test("invalid or ambiguous interval lists fail atomically, without a partial result", () => {
  for (const value of ["", ";\n;", "1-3", "chrX:0-3", "chrX:4-3", "chrX:1.2-3", "chrX:1-3,bad", "chrX:1-3,",
    "chrX:1,00-300", "chrX:1,000-2,000,3,000-4,000", "chrX:1-25000001", "chrX:9007199254740993-9007199254740994", "x".repeat(12001)]) {
    assert.throws(() => parseHighlightInput(value), /./u, value);
  }
});

test("events deduplicate exact intervals but preserve distinct overlapping or adjacent ranges with stable colors", () => {
  const events = parseHighlightInput("chrX:1-3,1-3,2-4,4-5");
  assert.deepEqual(events, [locus(0, 3), locus(1, 4), locus(3, 5)]);
  assert.equal(highlightKey(events[0]), "chrX:1-3");
  assert.equal(highlightColor(events[0]), highlightColor({ ...events[0] }));
  assert.throws(() => validateHighlights(Array.from({ length: MAX_EVENT_HIGHLIGHTS + 1 }, (_, i) => locus(i, i + 1))), /at most 100/);
  assert.throws(() => validateHighlights([{ chrom: "<script>", start0: 0, end0: 3 }]), /valid/);
});

test("active-assembly bounds reject unknown contigs and positions beyond chromosome length", () => {
  checkHighlightBounds([locus(0, 100)], { chrX: 100 });
  checkHighlightBounds([], undefined);
  assert.throws(() => checkHighlightBounds([locus(0, 1)]), /bounds are unavailable/);
  assert.throws(() => checkHighlightBounds([locus(99, 101)], { chrX: 100 }), /exceeds/);
  assert.throws(() => checkHighlightBounds([locus(0, 1, "chrY")], { chrX: 100 }), /not in/);
});

test("positive-strand event projects exon-overlapping bases onto RNA and touched codons", () => {
  const projection = projectGenomicEvent(locus(108, 202), chr, transcript());
  assert.deepEqual(projection.rna, [{ start1: 9, end1: 10, exonRank: 1 }, { start1: 11, end1: 12, exonRank: 2 }]);
  assert.deepEqual(projection.protein, [{ start1: 2, end1: 3 }]);
  assert.equal(projection.partialCodons, true);
});

test("negative-strand event retains biological transcript/protein order", () => {
  const projection = projectGenomicEvent(locus(118, 202), chr, transcript("-"));
  assert.deepEqual(projection.rna, [{ start1: 9, end1: 10, exonRank: 1 }, { start1: 11, end1: 12, exonRank: 2 }]);
  assert.deepEqual(projection.protein, [{ start1: 2, end1: 3 }]);
  assert.equal(projection.partialCodons, true);
});

test("a complete codon spanning an exon junction is not mislabeled as a partial codon on either strand", () => {
  assert.equal(projectGenomicEvent(locus(105, 201), chr, transcript()).partialCodons, false);
  assert.equal(projectGenomicEvent(locus(119, 205), chr, transcript("-")).partialCodons, false);
  assert.deepEqual(projectGenomicEvent(locus(105, 201), chr, transcript()).protein, [{ start1: 1, end1: 2 }]);
});

test("introns, UTRs, noncoding transcripts, unavailable details and other chromosomes remain distinguishable", () => {
  const tx = transcript();
  assert.equal(projectGenomicEvent(locus(110, 200), chr, tx).state, "intronic");
  assert.match(projectGenomicEvent(locus(100, 105), chr, tx).proteinReason, /outside translated CDS/);
  assert.match(projectGenomicEvent(locus(205, 210), chr, transcript("-")).proteinReason, /outside translated CDS/);
  assert.match(projectGenomicEvent(locus(100, 110), chr, { ...tx, proteinLength: 0, codingSegments: [] }).proteinReason, /No translated product/);
  assert.equal(projectGenomicEvent(locus(100, 110), chr, { ...tx, detailState: "loading" }).state, "loading");
  assert.equal(projectGenomicEvent(locus(100, 110), chr, { ...tx, detailState: "error" }).state, "error");
  assert.equal(projectGenomicEvent(locus(100, 110, "chr2"), chr, tx).state, "outside");
  assert.equal(projectGenomicEvent(locus(220, 221), chr, tx).state, "outside");
});

test("partial and unresolved coding maps never gain protein positions", () => {
  for (const status of ["partial", "unresolved", "unknown", "unmapped"]) {
    const projection = projectGenomicEvent(locus(100, 220), chr, { ...transcript(), translationMapping: { status, reason: "Not exact" } });
    assert.equal(projection.rna.length, 2);
    assert.deepEqual(projection.protein, []);
    assert.match(projection.proteinReason, /Not projected/);
  }
});

test("inconsistent exact maps fail closed, including RNA gaps, reordered CDS pieces and mismatched origins", () => {
  const tx = transcript();
  const first = tx.codingSegments![0], second = tx.codingSegments![1];
  const invalid: Transcript[] = [
    { ...tx, codingSegments: [] }, { ...tx, proteinLength: 5 },
    { ...tx, codingSegments: [first, { ...second, codingStart0: 6 }] },
    { ...tx, codingSegments: [first, { ...second, start0: 201, end0: second.end0 + 1 }] },
    { ...tx, codingSegments: [{ ...first, exonRank: 2 }, second] },
    { ...tx, codingSegments: [{ ...second, codingStart0: 0, codingEnd0: 13 }, { ...first, codingStart0: 13, codingEnd0: 18 }] },
    { ...tx, translationMapping: { ...tx.translationMapping!, cdsStart0: 4 } },
    { ...tx, translationMapping: { ...tx.translationMapping!, cdsEnd0: 24 } },
  ];
  for (const broken of invalid) assert.deepEqual(projectGenomicEvent(locus(100, 220), chr, broken).protein, []);
  const badExons = [
    { ...tx, transcriptLength: 29 },
    { ...tx, exons: tx.exons.map((exon) => ({ ...exon, rank: 1 })) },
    { ...tx, exons: [{ ...tx.exons[0], transcriptStart0: 1 }, tx.exons[1]] },
    { ...tx, exons: [{ ...tx.exons[0], transcriptEnd0: 9 }, tx.exons[1]] },
  ];
  for (const broken of badExons) assert.equal(projectGenomicEvent(locus(100, 220), chr, broken).state, "error");
});

test("single-base and whole-CDS highlights obey half-open boundaries and do not include flanking UTR/stop bases", () => {
  const tx = transcript();
  assert.deepEqual(projectGenomicEvent(locus(105, 106), chr, tx).protein, [{ start1: 1, end1: 1 }]);
  assert.deepEqual(projectGenomicEvent(locus(212, 213), chr, tx).protein, [{ start1: 6, end1: 6 }]);
  assert.deepEqual(projectGenomicEvent(locus(213, 216), chr, tx).protein, []);
  const full = projectGenomicEvent(locus(100, 220), chr, tx);
  assert.deepEqual(full.protein, [{ start1: 1, end1: 6 }]);
  assert.equal(full.partialCodons, false);
  const withStopInHeader = { ...tx, translationMapping: { ...tx.translationMapping!, cdsEnd0: 26 } };
  assert.deepEqual(projectGenomicEvent(locus(100, 220), chr, withStopInHeader).protein, full.protein);
  assert.deepEqual(projectGenomicEvent(locus(213, 216), chr, withStopInHeader).protein, []);
});

test("phase-one/two split codons on both strands agree with an independent per-base oracle for every small interval", () => {
  for (const strand of ["+", "-"] as const) for (const firstLength of [4, 5]) {
    const tx = transcript(strand, firstLength);
    const rnaBases: { g: number; rna1: number; exonRank: number }[] = [];
    for (const exon of tx.exons) for (let i = 0; i < exon.end0 - exon.start0; i++) {
      rnaBases.push({ g: strand === "+" ? exon.start0 + i : exon.end0 - 1 - i, rna1: rnaBases.length + 1, exonRank: exon.rank });
    }
    const codingBases: { g: number; aa1: number }[] = [];
    for (const piece of tx.codingSegments!) for (let i = 0; i < piece.end0 - piece.start0; i++) {
      codingBases.push({ g: strand === "+" ? piece.start0 + i : piece.end0 - 1 - i, aa1: Math.floor(codingBases.length / 3) + 1 });
    }
    for (let start = 99; start < 221; start++) for (let end = start + 1; end <= 221; end++) {
      const actual = projectGenomicEvent(locus(start, end), chr, tx);
      const rna = tx.exons.flatMap((exon) => {
        const touched = rnaBases.filter((base) => base.exonRank === exon.rank && base.g >= start && base.g < end);
        return touched.length ? [{ start1: touched[0].rna1, end1: touched.at(-1)!.rna1, exonRank: exon.rank }] : [];
      });
      const aaCounts = new Map<number, number>();
      for (const base of codingBases) if (base.g >= start && base.g < end) aaCounts.set(base.aa1, (aaCounts.get(base.aa1) ?? 0) + 1);
      const touchedAas = [...aaCounts.keys()];
      const protein = touchedAas.length ? [{ start1: touchedAas[0], end1: touchedAas.at(-1)! }] : [];
      assert.deepEqual(actual.rna, rna);
      assert.deepEqual(actual.protein, protein);
      assert.equal(actual.partialCodons, [...aaCounts.values()].some((count) => count < 3));
    }
  }
});

test("event state round-trips through URL, workspace and portable sessions without changing legacy view shape", () => {
  const legacy = { ...DEFAULT_VIEW_STATE, selectedFeatureId: undefined };
  assert.deepEqual(parseViewState(encodeViewState(legacy), legacy), legacy);
  const view = { ...legacy, genomicHighlights: parseHighlightInput("chrX:1-3,5-9,22-50") };
  assert.equal(hasExplicitViewState("?hi="), true);
  assert.deepEqual(parseViewState(encodeViewState(view), legacy), view);
  assert.deepEqual(parsePortableSession(encodeSession(view), legacy, view.buildHash).view, view);
  const workspace = { ...createEmptyWorkspaceState(view.buildHash), lastView: view };
  assert.deepEqual(parseWorkspaceState(serializeWorkspaceState(workspace), view.buildHash).lastView, JSON.parse(JSON.stringify(view)));
  assert.deepEqual(parseViewState("?hi=", view).genomicHighlights, []);
  assert.deepEqual(parseViewState("?hi=chrX%3A1-3%2Cbad", view).genomicHighlights, []);
});

test("malformed portable sessions and foreign-build URLs do not apply event intervals", () => {
  const view = { ...DEFAULT_VIEW_STATE, genomicHighlights: [locus(0, 3)] };
  const encoded = JSON.parse(encodeSession(view));
  encoded.urlState = encoded.urlState.replace(/hi=[^&]*/u, "hi=chrX%3A1-3%2Cbad");
  assert.throws(() => parsePortableSession(JSON.stringify(encoded), DEFAULT_VIEW_STATE, view.buildHash), /Use chrX/);
  const other = { ...view, buildHash: "another-build" };
  assert.equal(restoreViewState(encodeViewState(other), DEFAULT_VIEW_STATE, view.buildHash).view.genomicHighlights, undefined);
});

test("event editor exposes accessible controls, transcript/protein projections and explicit non-prediction provenance", () => {
  const tx = transcript(), gene: Gene = { ...SP1_GENE, chrom: chr, transcripts: [tx] };
  const html = renderToStaticMarkup(createElement(EventHighlights, {
    highlights: [locus(108, 202), locus(110, 200)], chromosomeLengths: { chrX: 1000 }, gene, selected: tx,
    comparison: { ...tx, id: "TX_OTHER", name: "TEST-202", translationMapping: { status: "partial", reason: "Partial" } },
    onChange: () => undefined, onNavigate: () => undefined,
  }));
  assert.match(html, /<details class="event-highlights"/);
  assert.match(html, /Genomic intervals/);
  assert.match(html, /Add highlights/);
  assert.match(html, /Fit highlights/);
  assert.match(html, /Clear highlights/);
  assert.match(html, /aria-label="Remove highlight chrX:109-202"/);
  assert.match(html, /data-projection-state="exonic" data-protein-ranges="2–3"/);
  assert.match(html, /data-projection-state="intronic"/);
  assert.match(html, /Not projected: partial coding map/);
  assert.match(html, /partial codon overlap/);
  assert.match(html, /not annotation evidence or predicted splice\/protein changes/);
  assert.match(html, /TEST-202 · event projection/);
});
