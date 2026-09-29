import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_VIEW_STATE, SP1_GENE } from "../src/data/sp1";
import { filterTranscriptsWithContext } from "../src/lib/filters";

test("the default view does not hide low-support, unscored, noncoding, or incomplete transcripts", () => {
  const template = SP1_GENE.transcripts[0];
  const models = ["1", "2", "3", "4", "5", "", "NA"].map((tsl, index) => ({
    ...template,
    id: `synthetic-${index}`,
    tsl,
    biotype: index % 2 ? "lncRNA" : "protein_coding",
    tags: index === 4 ? ["cds_start_NF"] : [],
    badges: [],
  }));
  assert.deepEqual(DEFAULT_VIEW_STATE.excludedTranscriptBiotypes, []);
  assert.deepEqual(DEFAULT_VIEW_STATE.activeTranscriptFlags, []);
  const retained = filterTranscriptsWithContext(
    models,
    DEFAULT_VIEW_STATE.excludedTranscriptBiotypes,
    DEFAULT_VIEW_STATE.activeTranscriptFlags,
    "",
    [],
  );
  assert.deepEqual(retained.map((model) => model.id), models.map((model) => model.id));
});
