import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TranscriptLabels } from "../src/components/TranscriptLabels";
import { DEFAULT_VIEW_STATE, SP1_GENE } from "../src/data/sp1";
import { buildRowLayout } from "../src/lib/layout";

const translated = SP1_GENE.transcripts.filter((transcript) => transcript.proteinLength > 0).slice(0, 2);
const gene = { ...SP1_GENE, transcripts: translated };
const ids = translated.map((transcript) => transcript.id);
const callbacks = {
  onSelectTranscript: () => undefined,
  onToggleExpanded: () => undefined,
  onTogglePinned: () => undefined,
  onSetComparison: () => undefined,
  onReorderTranscript: () => undefined,
  onReorderFocusHandled: () => undefined,
};

function renderLabels(displayMode: "labeled" | "expanded", expandedTranscriptIds: string[], items = translated) {
  return renderToStaticMarkup(createElement(TranscriptLabels, {
    gene: { ...gene, transcripts: items },
    transcripts: items,
    layout: buildRowLayout(items, expandedTranscriptIds, DEFAULT_VIEW_STATE.activeSources),
    displayMode,
    selectedTranscriptId: ids[0],
    comparisonTranscriptId: "",
    selectedTranscriptName: translated[0].name,
    expandedTranscriptIds,
    pinnedTranscriptIds: [],
    reorderableTranscriptIds: ids,
    customOrderActive: false,
    activeSources: DEFAULT_VIEW_STATE.activeSources,
    rowDensity: "comfortable",
    locus: DEFAULT_VIEW_STATE.locus,
    ...callbacks,
  }));
}

test("multiple translated transcript rows expose independent expanded controls", () => {
  const html = renderLabels("expanded", ids);
  assert.equal((html.match(/aria-expanded="true"/g) ?? []).length, 2);
  assert.match(html, new RegExp(`Collapse ${translated[0].name} protein annotations`));
  assert.match(html, new RegExp(`Collapse ${translated[1].name} protein annotations`));
});

test("a translated transcript can open protein features from another track-content mode", () => {
  const html = renderLabels("labeled", []);
  assert.match(html, new RegExp(`aria-label="Expand ${translated[0].name} protein annotations"`));
  assert.doesNotMatch(html, new RegExp(`aria-label="Expand ${translated[0].name} protein annotations"[^>]*disabled`));
});

test("idle expanded rows indicate loading rather than successful empty coverage", () => {
  const html = renderLabels("expanded", ids, translated.map((item) => ({ ...item, features: [], featuresState: "idle" as const })));
  assert.match(html, /Loading local protein annotations/);
  assert.doesNotMatch(html, /No features in the selected local sources/);
});

test("successfully loaded empty rows preserve an explicit no-feature state", () => {
  const html = renderLabels("expanded", ids, translated.map((item) => ({ ...item, features: [], featuresState: "ready" as const })));
  assert.match(html, /No features in the selected local sources/);
  assert.doesNotMatch(html, /Loading local protein annotations/);
});
