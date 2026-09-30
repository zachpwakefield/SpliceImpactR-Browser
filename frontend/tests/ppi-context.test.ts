import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SP1_GENE, FALLBACK_MANIFEST } from "../src/data/sp1";
import { observePPIToken, ppiTokenSource } from "../src/lib/ppiContext";
import { PPIContextPanel } from "../src/components/PPIContextPanel";
import { validateGenePPIContext } from "../src/api";
import { readFileSync } from "node:fs";
import type { BuildManifest, GenePPIContext, ProteinFeature, Transcript } from "../src/types";

const transcript: Transcript = { ...SP1_GENE.transcripts[0], featuresState: "ready", features: [] };
const manifest: BuildManifest = { ...FALLBACK_MANIFEST, species: "human", featureSources: ["pfam", "elm", "interpro"],
  featureAvailability: { pfam: { status: "available" }, elm: { status: "available-empty" }, interpro: { status: "available" } } };
function call(featureId: string, source: ProteinFeature["source"]): ProteinFeature {
  return { recordId: `record-${featureId}`, transcriptId: transcript.id, featureId, source, method: source,
    name: featureId, aaStart: 1, aaEnd: 20, projectionStatus: "partial", segments: [] };
}
test("PPI namespaces are explicit and preserve literal real ELM class identifiers", () => {
  assert.equal(ppiTokenSource("PF00162"), "pfam");
  assert.equal(ppiTokenSource("IPR001487"), "interpro");
  for (const token of ["LIG_14-3-3_CanoR_1", "CLV_C14_Caspase3-7", "MOD_SUMO_rev_2", "DOC_MAPK_HePTP_8", "TRG_ER_FFAT_1"]) {
    assert.equal(ppiTokenSource(token), "elm");
  }
  assert.equal(ppiTokenSource("SM00028"), undefined);
  assert.equal(ppiTokenSource("unknown motif name"), undefined);
});
test("PPI token observations require exact source and accession, never feature name or fuzzy version matching", () => {
  const t = { ...transcript, features: [{ ...call("PF00162", "interpro"), name: "PF00162" }, call("PF00162.1", "pfam")] };
  assert.equal(observePPIToken("PF00162", t, manifest).state, "not-observed");
  assert.equal(observePPIToken("PF00162.1", t, manifest).state, "observed");
  assert.equal(observePPIToken("PF00162", { ...t, features: [call("PF00162", "pfam")] }, manifest).state, "observed");
});
test("partial genomic mapping does not turn a stored AA annotation observation into an interaction prediction", () => {
  const value = observePPIToken("PF00162", { ...transcript, features: [call("PF00162", "pfam")] }, manifest);
  assert.equal(value.state, "observed");
  assert.equal(value.calls[0].projectionStatus, "partial");
  assert.deepEqual(value.calls[0].segments, []);
  assert.equal("prediction" in value, false);
});
test("missing source, unresolved namespace, product, loading and errors remain not assessed", () => {
  assert.equal(observePPIToken("SM00028", transcript, manifest).state, "not-assessed");
  assert.equal(observePPIToken("PF00162", { ...transcript, proteinLength: 0 }, manifest).state, "not-assessed");
  for (const featuresState of ["idle", "loading", "error", undefined] as const) {
    assert.equal(observePPIToken("PF00162", { ...transcript, featuresState }, manifest).state, "not-assessed");
  }
  assert.equal(observePPIToken("PF00162", transcript, { ...manifest, featureSources: ["elm"] }).state, "not-assessed");
  assert.equal(observePPIToken("PF00162", transcript, { ...manifest, featureAvailability: { pfam: { status: "unavailable" } } }).state, "not-assessed");
});
test("only a valid empty available source can report a token not observed", () => {
  assert.equal(observePPIToken("LIG_PDZ_Class_1", transcript, manifest).state, "not-observed");
  const invalid = { ...transcript, features: [{ ...call("PF00162", "pfam"), transcriptId: "OTHER" }] };
  assert.equal(observePPIToken("PF00162", invalid, manifest).state, "not-assessed");
});
test("malformed or out-of-protein AA calls cannot become PPI feature evidence", () => {
  for (const bounds of [{ aaStart: 1.5, aaEnd: 20 }, { aaStart: 20, aaEnd: 1 }, { aaStart: 0, aaEnd: 20 },
    { aaStart: 1, aaEnd: transcript.proteinLength + 1 }]) {
    assert.equal(observePPIToken("PF00162", { ...transcript, features: [{ ...call("PF00162", "pfam"), ...bounds }] }, manifest).state, "not-assessed");
  }
  assert.equal(observePPIToken("PF00162", transcript, { ...manifest, species: "mouse" }).state, "not-assessed");
});
test("human PPI panel explicitly separates unavailable context from predictions", () => {
  const html = renderToStaticMarkup(createElement(PPIContextPanel, { geneId: SP1_GENE.id, manifest,
    selectedTranscript: transcript, comparisonTranscript: SP1_GENE.transcripts[1], onInspectFeature: () => undefined }));
  assert.match(html, /PPI context and focal feature evidence/);
  assert.match(html, /optional interaction context has not been prepared/);
  assert.match(html, /Partner isoforms and expression are not assessed/);
  assert.match(html, /Interaction-switch predictions are disabled/);
  assert.doesNotMatch(html, /0 total gene records/);
});
test("mouse PPI panel never applies the human network or claims empty interaction evidence", () => {
  const html = renderToStaticMarkup(createElement(PPIContextPanel, { geneId: "ENSMUSG00000000001", manifest: { ...manifest, species: "mouse" },
    selectedTranscript: transcript, comparisonTranscript: SP1_GENE.transcripts[1], onInspectFeature: () => undefined }));
  assert.match(html, /human-only/);
  assert.match(html, /never applied to mouse/);
  assert.doesNotMatch(html, /total gene records/);
});
test("real backend synthetic response passes frontend dataset and A/B/self endpoint validation", () => {
  // Checked for exact equality with PpiContextApiTests.endpoint(limit=3).
  const response: GenePPIContext = JSON.parse(readFileSync(new URL("../../tests/data/fixtures/ppi-context-api.example.json", import.meta.url), "utf8"));
  const m: BuildManifest = { ...manifest, datasetId: response.datasetId, buildHash: response.buildHash,
    ppiContext: { status: "loaded", provenance: response.provenance } };
  assert.equal(validateGenePPIContext(response, m, response.geneId, 0, "feature-linked", 3), response);
  assert.deepEqual(response.records.slice(0, 3).map(record => record.focalEndpoint), ["A", "B", "A+B"]);
  for (const broken of [{ ...response, buildHash: "wrong" }, { ...response, predictionAvailable: true },
    { ...response, records: [{ ...response.records[0], focalEndpoint: "B" }] },
    { ...response, records: [{ ...response.records[0], partner: { ...response.records[0].partner, id: response.geneId } }] }]) {
    assert.throws(() => validateGenePPIContext(broken as GenePPIContext, m, response.geneId, 0, "feature-linked", 3));
  }
});
