import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_VIEW_STATE, SP1_GENE } from "../src/data/sp1.ts";
import {
  MAX_COLLAPSED_PROTEIN_TRANSCRIPTS,
  MAX_EXPANDED_TRANSCRIPTS,
  effectiveProteinExpansionIds,
  normalizeProteinExpansionDefault,
  proteinExpansionDefaults,
} from "../src/lib/navigation.ts";
import { SESSION_FORMAT, encodeSession, parsePortableSession } from "../src/lib/session.ts";
import { encodeViewState, hasExplicitViewState, parseViewState } from "../src/lib/urlState.ts";
import { chooseInitialView } from "../src/lib/viewRestore.ts";
import {
  createEmptyWorkspaceState,
  decodeWorkspaceState,
  serializeWorkspaceState,
  withLastView,
} from "../src/lib/workspaceStore.ts";
import type { BrowserViewState, Transcript } from "../src/types.ts";

const BUILD = DEFAULT_VIEW_STATE.buildHash;

function transcript(index: number, proteinLength = 100): Transcript {
  return { ...SP1_GENE.transcripts[0], id: `ENST${String(index).padStart(11, "0")}`, proteinLength };
}

function view(overrides: Partial<BrowserViewState> = {}): BrowserViewState {
  return { ...DEFAULT_VIEW_STATE, selectedFeatureId: undefined, ...overrides };
}

function portableWithUrl(urlState: string): string {
  return JSON.stringify({ format: SESSION_FORMAT, version: 2, buildHash: BUILD, urlState, annotations: {} });
}

test("All uses a compact flag and expands every translated transcript, not a 25-row prefix", () => {
  const transcripts = [transcript(0, 0), ...Array.from({ length: 296 }, (_, index) => transcript(index + 1))];
  const defaults = proteinExpansionDefaults("all", transcripts);
  assert.deepEqual(defaults, {
    displayMode: "expanded", expandedTranscriptIds: [], expandAllProteins: true, collapsedProteinTranscriptIds: [],
  });
  assert.equal(MAX_EXPANDED_TRANSCRIPTS, 25);
  assert.deepEqual(effectiveProteinExpansionIds(transcripts, defaults), transcripts.slice(1).map((item) => item.id));
  assert.equal(new URLSearchParams(encodeViewState(view(defaults)).slice(1)).get("expanded"), "");
});

test("Top chooses only the first translation; None and untranslated genes stay collapsed", () => {
  const transcripts = [transcript(0, 0), transcript(1), transcript(2)];
  assert.deepEqual(proteinExpansionDefaults("top", transcripts), {
    displayMode: "expanded", expandedTranscriptIds: [transcripts[1].id], expandAllProteins: false, collapsedProteinTranscriptIds: [],
  });
  assert.deepEqual(proteinExpansionDefaults("none", transcripts), {
    displayMode: "labeled", expandedTranscriptIds: [], expandAllProteins: false, collapsedProteinTranscriptIds: [],
  });
  assert.deepEqual(proteinExpansionDefaults("top", [transcript(0, 0)]).expandedTranscriptIds, []);
  assert.deepEqual(proteinExpansionDefaults("top", []).expandedTranscriptIds, []);
  assert.deepEqual(effectiveProteinExpansionIds([transcript(0, 0)], proteinExpansionDefaults("all", [])), []);
});

test("missing or malformed preferences use Top without changing legacy workspace shape", () => {
  for (const candidate of [undefined, null, "ALL", "anything", false, 0, {}, []]) {
    assert.equal(normalizeProteinExpansionDefault(candidate), "top");
    assert.deepEqual(proteinExpansionDefaults(candidate, SP1_GENE.transcripts), proteinExpansionDefaults("top", SP1_GENE.transcripts));
  }
  const legacy = createEmptyWorkspaceState(BUILD);
  const loaded = decodeWorkspaceState(JSON.stringify(legacy), BUILD);
  assert.deepEqual(loaded.state, legacy);
  assert.equal(Object.hasOwn(loaded.state, "proteinExpansionDefault"), false);
  const malformed = decodeWorkspaceState(JSON.stringify({ ...legacy, proteinExpansionDefault: "unbounded" }), BUILD);
  assert.equal(malformed.status, "ready");
  assert.equal(malformed.state.proteinExpansionDefault, "top");
});

test("All respects independent collapse exceptions while manual opens win and unknown IDs never create rows", () => {
  const transcripts = [transcript(0, 0), transcript(1), transcript(2), transcript(3)];
  const state = view({
    ...proteinExpansionDefaults("all", transcripts),
    expandedTranscriptIds: [transcripts[0].id, transcripts[2].id, "ENST99999999999"],
    collapsedProteinTranscriptIds: [transcripts[1].id, transcripts[2].id, "ENST88888888888"],
  });
  assert.deepEqual(effectiveProteinExpansionIds(transcripts, state), [transcripts[0].id, transcripts[2].id, transcripts[3].id]);
  const saved = withLastView(createEmptyWorkspaceState(BUILD), state).lastView!;
  assert.deepEqual(saved.collapsedProteinTranscriptIds, [transcripts[1].id, "ENST88888888888"]);
  assert.deepEqual(effectiveProteinExpansionIds(transcripts, { ...state, expandAllProteins: false }), [transcripts[0].id, transcripts[2].id]);
});

test("saved preferences and All disclosure overrides round-trip through the workspace", () => {
  const transcripts = [transcript(0), transcript(1), transcript(2)];
  const allView = view({ ...proteinExpansionDefaults("all", transcripts), collapsedProteinTranscriptIds: [transcripts[1].id] });
  for (const proteinExpansionDefault of ["all", "top", "none"] as const) {
    const state = withLastView({ ...createEmptyWorkspaceState(BUILD), proteinExpansionDefault }, allView);
    assert.deepEqual(decodeWorkspaceState(serializeWorkspaceState(state), BUILD).state, state);
  }
});

test("invalid saved disclosure flags, unsafe IDs and oversized exception sets cannot be restored", () => {
  const legacy = createEmptyWorkspaceState(BUILD);
  const invalidOverrides = [
    { expandAllProteins: "yes" },
    { collapsedProteinTranscriptIds: "ENST00000000001" },
    { collapsedProteinTranscriptIds: ["unsafe ID"] },
    { collapsedProteinTranscriptIds: ["x".repeat(81)] },
    { collapsedProteinTranscriptIds: Array.from({ length: MAX_COLLAPSED_PROTEIN_TRANSCRIPTS + 1 }, (_, index) => transcript(index).id) },
  ];
  for (const overrides of invalidOverrides) {
    const loaded = decodeWorkspaceState(JSON.stringify({ ...legacy, proteinExpansionDefault: "all", lastView: { ...view(), ...overrides } }), BUILD);
    assert.equal(loaded.status, "ready");
    assert.equal(loaded.state.proteinExpansionDefault, "all");
    assert.equal(loaded.state.lastView, undefined);
  }
});

test("All flag and up to 500 collapse exceptions survive URL and portable-session round trips", () => {
  const state = view({
    ...proteinExpansionDefaults("all", []),
    collapsedProteinTranscriptIds: Array.from({ length: MAX_COLLAPSED_PROTEIN_TRANSCRIPTS }, (_, index) => transcript(index).id),
  });
  assert.deepEqual(parseViewState(encodeViewState(state), DEFAULT_VIEW_STATE), state);
  assert.deepEqual(parsePortableSession(encodeSession(state), DEFAULT_VIEW_STATE, BUILD).view, state);
  assert.equal(hasExplicitViewState("?allProteins=0"), true);
  assert.equal(hasExplicitViewState("?collapsedProteins="), true);
  assert.equal(hasExplicitViewState("?supportPanel=1"), false);
  const withoutOptionalFields = view();
  assert.deepEqual(parseViewState(encodeViewState(withoutOptionalFields), DEFAULT_VIEW_STATE), withoutOptionalFields);
});

test("URL imports sanitize and bound collapse exceptions; portable files reject malformed expansion metadata", () => {
  const ids = Array.from({ length: MAX_COLLAPSED_PROTEIN_TRANSCRIPTS + 3 }, (_, index) => transcript(index).id);
  const parsed = parseViewState(`?allProteins=1&expanded=&collapsedProteins=${ids.join(",")}`, DEFAULT_VIEW_STATE);
  assert.deepEqual(parsed.collapsedProteinTranscriptIds, ids.slice(0, MAX_COLLAPSED_PROTEIN_TRANSCRIPTS));
  const unsafe = parseViewState("?allProteins=true&expanded=&collapsedProteins=unsafe%20ID,ENST00000000001,ENST00000000001", DEFAULT_VIEW_STATE);
  assert.equal(unsafe.expandAllProteins, false);
  assert.deepEqual(unsafe.collapsedProteinTranscriptIds, ["ENST00000000001"]);
  const base = new URLSearchParams(encodeViewState(view()).slice(1));
  base.set("allProteins", "true");
  assert.throws(() => parsePortableSession(portableWithUrl(`?${base}`), DEFAULT_VIEW_STATE, BUILD), /invalid protein-expansion flag/);
  base.set("allProteins", "1");
  base.set("collapsedProteins", "unsafe ID");
  assert.throws(() => parsePortableSession(portableWithUrl(`?${base}`), DEFAULT_VIEW_STATE, BUILD), /protein-collapse exceptions/);
  base.set("collapsedProteins", ids.join(","));
  assert.throws(() => parsePortableSession(portableWithUrl(`?${base}`), DEFAULT_VIEW_STATE, BUILD), /500-transcript limit/);
});

test("explicit old views and sessions do not inherit a new All preference", () => {
  const allFallback = view(proteinExpansionDefaults("all", SP1_GENE.transcripts));
  const oldView = view({ displayMode: "labeled", expandedTranscriptIds: [] });
  const restored = parseViewState(encodeViewState(oldView), allFallback);
  assert.equal(restored.expandAllProteins, false);
  assert.deepEqual(restored.collapsedProteinTranscriptIds, []);
  assert.deepEqual(effectiveProteinExpansionIds(SP1_GENE.transcripts, restored), []);
  const legacySession = JSON.stringify({ format: SESSION_FORMAT, version: 1, buildHash: BUILD, urlState: encodeViewState(oldView) });
  assert.equal(parsePortableSession(legacySession, allFallback, BUILD).view.expandAllProteins, false);
});

test("explicit and automatically restored disclosure state take precedence over the default preference", () => {
  const saved = view({ ...proteinExpansionDefaults("all", SP1_GENE.transcripts), collapsedProteinTranscriptIds: [SP1_GENE.transcripts[0].id] });
  const workspace = { ...createEmptyWorkspaceState(BUILD), proteinExpansionDefault: "none" as const, lastView: saved };
  const defaultView = view(proteinExpansionDefaults("none", SP1_GENE.transcripts));
  assert.deepEqual(chooseInitialView("", defaultView, workspace), { view: saved, restoredLastView: true });
  assert.deepEqual(chooseInitialView("?allProteins=0", defaultView, workspace), { view: defaultView, restoredLastView: false });
});
