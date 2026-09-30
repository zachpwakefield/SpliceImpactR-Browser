import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FeatureComparisonPanel } from "../src/components/FeatureComparisonPanel";
import { SP1_GENE, FALLBACK_MANIFEST } from "../src/data/sp1";
import { buildFeatureComparison, filterFeatureComparison } from "../src/lib/featureComparison";
import { FEATURE_COMPARISON_EXPORT_COLUMNS, serializeFeatureComparison } from "../src/lib/featureComparisonExport";
import { buildTranscriptComparison, comparisonCellExportValue, transcriptFeatureCountCell } from "../src/lib/comparison";
import { buildComparisonExportRows } from "../src/lib/comparisonExport";
import type { FeatureSource, ProteinFeature, Transcript } from "../src/types";

function call(transcriptId: string, recordId: string, aaStart = 10, aaEnd = 30, accession = "PF00001", source: FeatureSource = "pfam", method = "Pfam"): ProteinFeature {
  return { transcriptId, recordId, aaStart, aaEnd, featureId: accession, source, method, name: `Name ${accession}`,
    projectionStatus: "exact", segments: [] };
}
function transcript(id: string, features: ProteinFeature[] = []): Transcript {
  return { ...SP1_GENE.transcripts[0], id, versionedId: `${id}.1`, name: id, geneId: SP1_GENE.id,
    features, detailState: "ready", featuresState: "ready", proteinLength: 100 };
}
function pair(a: ProteinFeature[] = [], b: ProteinFeature[] = []) {
  return [transcript("A", a), transcript("B", b)] as const;
}

test("feature identities compare source/accession/method and not transcript-specific record IDs", () => {
  const [a, b] = pair([call("A", "a")], [call("B", "b")]);
  const model = buildFeatureComparison(a, b);
  assert.equal(model.state, "ready");
  assert.equal(model.rows[0].difference, "same");
  assert.equal(model.rows[0].selected[0].recordId, "a");
  assert.equal(model.rows[0].comparison[0].recordId, "b");
});
test("one-sided source observations are not labeled biological gains or losses", () => {
  const [a, b] = pair([call("A", "a")], [call("B", "b", 1, 9, "PF00002")]);
  assert.deepEqual(buildFeatureComparison(a, b).rows.map(row => row.difference), ["selected-only", "comparison-only"]);
});
test("equal-count coordinate shifts are distinguished from accession differences", () => {
  const [a, b] = pair([call("A", "a")], [call("B", "b", 20, 40)]);
  assert.equal(buildFeatureComparison(a, b).rows[0].difference, "intervals-diff");
});
test("repeat call multiplicity is preserved even when intervals coincide", () => {
  const [a, b] = pair([call("A", "a1"), call("A", "a2")], [call("B", "b")]);
  const row = buildFeatureComparison(a, b).rows[0];
  assert.equal(row.difference, "call-count-diff");
  assert.equal(row.selected.length, 2);
});
test("multiset interval comparison is deterministic without inventing repeat correspondence", () => {
  const [a, b] = pair([call("A", "a1", 50, 60), call("A", "a2", 10, 20)],
    [call("B", "b2", 10, 20), call("B", "b1", 50, 60)]);
  const row = buildFeatureComparison(a, b).rows[0];
  assert.equal(row.difference, "same");
  assert.deepEqual(row.selected.map(call => call.aaStart), [10, 50]);
});
test("the same accession token in different sources or methods is never merged", () => {
  const [a, b] = pair([call("A", "a")], [call("B", "b1", 10, 30, "PF00001", "interpro"), call("B", "b2", 10, 30, "PF00001", "pfam", "Other method")]);
  const rows = buildFeatureComparison(a, b).rows;
  assert.equal(rows.length, 3);
  assert.ok(rows.every(row => row.difference !== "same"));
});
test("partial mapping remains comparable in amino acids and is not projected", () => {
  const partial = { ...call("A", "a"), projectionStatus: "partial", mappingReason: "Incomplete CDS", segments: [] };
  const [a, b] = pair([partial], [call("B", "b")]);
  const model = buildFeatureComparison(a, b);
  assert.equal(model.rows[0].difference, "same");
  assert.deepEqual(model.rows[0].selected[0].segments, []);
  const html = renderToStaticMarkup(createElement(FeatureComparisonPanel, { selectedTranscript: a, comparisonTranscript: b, sources: ["pfam"] }));
  // Shared calls are hidden initially, so render a coordinate-different call.
  const changed = { ...b, features: [call("B", "b", 11, 30)] };
  const visible = renderToStaticMarkup(createElement(FeatureComparisonPanel, { selectedTranscript: a, comparisonTranscript: changed, sources: ["pfam"] }));
  assert.match(visible, /AA only · partial/);
  assert.doesNotMatch(html, /No feature calls were observed/);
});
test("original out-of-protein bounds are preserved and explicitly labeled", () => {
  const [a, b] = pair([call("A", "a", 80, 120)], []);
  const row = buildFeatureComparison(a, b).rows[0];
  assert.equal(row.selected[0].aaEnd, 120);
  const html = renderToStaticMarkup(createElement(FeatureComparisonPanel, { selectedTranscript: a, comparisonTranscript: b, sources: ["pfam"] }));
  assert.match(html, /Outside stored protein bounds/);
});
test("loading, errors and missing products never become one-sided absence evidence", () => {
  const [a, b] = pair([call("A", "a")], []);
  for (const featuresState of [undefined, "idle", "loading", "error"] as const) {
    const model = buildFeatureComparison(a, { ...b, featuresState });
    assert.notEqual(model.state, "ready");
    assert.deepEqual(model.rows, []);
  }
  assert.equal(buildFeatureComparison(a, { ...b, proteinLength: 0 }).state, "not-applicable");
});
test("successful valid-empty sources produce genuine one-sided observations", () => {
  const [a, b] = pair([call("A", "a")], []);
  assert.equal(buildFeatureComparison(a, b, ["pfam"], { pfam: { status: "available" } }).rows[0].difference, "selected-only");
  assert.deepEqual(buildFeatureComparison(b, { ...b, id: "C", versionedId: "C.1" }, ["pfam"], { pfam: { status: "available-empty" } }).rows, []);
});
test("unavailable sources are excluded and never displayed or exported as zero", () => {
  const [a, b] = pair([call("A", "a")], []);
  const availability = { pfam: { status: "unavailable" as const, reason: "No species data" } };
  const model = buildFeatureComparison(a, b, ["pfam"], availability);
  assert.deepEqual(model.rows, []);
  assert.equal(model.unavailableSources[0].reason, "No species data");
  assert.equal(transcriptFeatureCountCell(b, "pfam", availability).state, "unavailable");
  assert.equal(comparisonCellExportValue(transcriptFeatureCountCell(b, "pfam", availability)), "Unavailable source");
  const metrics = buildTranscriptComparison(a, b, ["pfam"], availability);
  assert.equal(metrics.rows.find(row => row.key === "feature-count-pfam")?.comparison.display, "Unavailable source");
  const exported = buildComparisonExportRows(FALLBACK_MANIFEST.buildHash, SP1_GENE, [{ transcript: a, selected: true, comparison: false, pinned: false }], undefined,
    { ...FALLBACK_MANIFEST, featureAvailability: availability });
  assert.equal(exported[0].feature_count_pfam, "Unavailable source");
});
test("cross-gene, same-transcript and malformed feature ownership stop comparison", () => {
  const [a, b] = pair([call("A", "a")], []);
  assert.equal(buildFeatureComparison(a, a).state, "invalid");
  assert.equal(buildFeatureComparison(a, { ...b, geneId: "OTHER" }).state, "invalid");
  assert.equal(buildFeatureComparison({ ...a, features: [call("B", "bad")] }, b).state, "invalid");
  assert.equal(buildFeatureComparison({ ...a, features: [call("A", "bad", 0, 20)] }, b).state, "invalid");
});
test("unidentified calls never match each other or imply an accession loss", () => {
  const [a, b] = pair([call("A", "a", 1, 20, "local-record")], [call("B", "b", 1, 20, "local-record")]);
  const rows = buildFeatureComparison(a, b).rows;
  assert.equal(rows.length, 2);
  assert.ok(rows.every(row => row.difference === "unidentified"));
});
test("filtering compares names/accessions/methods and keeps shared calls optional", () => {
  const [a, b] = pair([call("A", "a1"), call("A", "a2", 1, 9, "PF00002")], [call("B", "b")]);
  const rows = buildFeatureComparison(a, b).rows;
  assert.equal(filterFeatureComparison(rows, "", true).length, 1);
  assert.equal(filterFeatureComparison(rows, "pf00001", false).length, 1);
  assert.equal(filterFeatureComparison(rows, "name PF00002", false).length, 1);
  assert.equal(filterFeatureComparison(rows, "absent", false).length, 0);
});
test("comparison cards and repeated calls have bounded initial DOM and accessible actions", () => {
  const calls = Array.from({ length: 20 }, (_, i) => call("A", `a${i}`, 1, 5, `PF${String(i).padStart(5, "0")}`));
  calls.push(...Array.from({ length: 20 }, (_, i) => call("A", `repeat${i}`, 10, 20, "PF00000")));
  const [a, b] = pair(calls, []);
  const html = renderToStaticMarkup(createElement(FeatureComparisonPanel, { selectedTranscript: a, comparisonTranscript: b, sources: ["pfam"], onInspectFeature: () => undefined }));
  assert.equal((html.match(/class="feature-difference-row /g) ?? []).length, 12);
  assert.match(html, /Next features/);
  assert.match(html, /Next calls/);
  assert.match(html, /Inspect Pfam PF00000/);
  assert.match(html, /1-based inclusive/);
  assert.match(html, /not aligned residues/);
  assert.match(html, /do not prove biological gain or loss/);
});
test("exports retain complete call sets, explicit provenance, known-empty arrays and source availability", () => {
  const [a, b] = pair([call("A", "a")], []);
  const model = buildFeatureComparison(a, b);
  const manifest = { ...FALLBACK_MANIFEST, datasetId: "human-gencode-v45", species: "human" as const, ensemblRelease: 111 };
  const csv = serializeFeatureComparison(model, a, b, manifest, "csv");
  const tsv = serializeFeatureComparison(model, a, b, manifest, "tsv");
  assert.equal(csv.split("\n")[0], FEATURE_COMPARISON_EXPORT_COLUMNS.join(","));
  assert.match(csv, /provenance,human-gencode-v45/);
  assert.match(csv, /feature_identity,human-gencode-v45/);
  assert.match(csv, /selected-only/);
  assert.match(csv, /""recordId"":""a""/);
  assert.match(tsv, /"\[\{""recordId"":""a""/);
  assert.match(tsv, /\t\[\]\n/);
});
test("empty comparisons retain provenance without a fake feature identity, and incomplete exports fail", () => {
  const [a, b] = pair();
  const text = serializeFeatureComparison(buildFeatureComparison(a, b), a, b, FALLBACK_MANIFEST, "csv");
  assert.equal(text.trimEnd().split("\n").length, 2);
  assert.doesNotMatch(text, /^feature_identity,/m);
  assert.throws(() => serializeFeatureComparison(buildFeatureComparison(a, { ...b, featuresState: "loading" }), a, b, FALLBACK_MANIFEST, "tsv"));
});
test("feature export neutralizes formula-like source text without altering numeric protein lengths", () => {
  const [a, b] = pair([call("A", "a", 1, 20, "=HYPERLINK(\"evil\")", "pfam", "@SUM(1)")], []);
  const text = serializeFeatureComparison(buildFeatureComparison(a, b), a, b, FALLBACK_MANIFEST, "tsv");
  assert.match(text, /'@SUM\(1\)/);
  assert.match(text, /'=HYPERLINK/);
  assert.match(text, /\t100\t/);
});
