import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { datasetUrl, normalizeManifest } from "../src/api.ts";
import { DEFAULT_VIEW_STATE } from "../src/data/sp1.ts";
import { manifestDefaultView } from "../src/lib/viewRestore.ts";
import { encodeViewState, parseViewState } from "../src/lib/urlState.ts";
import { encodeSession, parsePortableSession } from "../src/lib/session.ts";
import { createEmptyWorkspaceState, loadWorkspaceState, saveWorkspaceState, clearWorkspaceState, WORKSPACE_STORAGE_KEY, workspaceStorageKey } from "../src/lib/workspaceStore.ts";

const mouse = {
  datasetId: "mouse-gencode-m39", species: "mouse", label: "Mouse · GENCODE M39",
  release: "GENCODE M39", ensemblRelease: 116, assembly: "GRCm39", buildHash: "mouse-build",
  defaultView: { selectedGeneId: "ENSMUSG00000001280", selectedTranscriptId: "ENSMUST00000001305", locus: { chrom: "chr15", start0: 100, end0: 200 } },
};

test("new dataset manifests require explicit species, assembly and Ensembl identity", () => {
  const manifest = normalizeManifest(mouse);
  assert.equal(manifest.species, "mouse");
  assert.equal(manifest.ensemblRelease, 116);
  assert.equal(manifest.assembly, "GRCm39");
  assert.throws(() => normalizeManifest({ ...mouse, ensemblRelease: undefined }), /Ensembl release/);
  assert.throws(() => normalizeManifest({ ...mouse, species: undefined }), /species/);
  assert.throws(() => normalizeManifest({ ...mouse, assembly: undefined }), /assembly/);
});

test("mouse uses its own validated starting view, never the human fixture locus", () => {
  const view = manifestDefaultView(normalizeManifest(mouse));
  assert.equal(view.datasetId, mouse.datasetId);
  assert.equal(view.selectedGeneId, mouse.defaultView.selectedGeneId);
  assert.deepEqual(view.locus, mouse.defaultView.locus);
  assert.deepEqual(view.expandedTranscriptIds, []);
  assert.equal(view.comparisonTranscriptId, "");
  assert.throws(() => manifestDefaultView(normalizeManifest({ ...mouse, defaultView: undefined })), /starting gene/);
});

test("dataset identity survives URLs and sessions; cross-dataset sessions are rejected", () => {
  const view = manifestDefaultView(normalizeManifest(mouse));
  assert.equal(parseViewState(encodeViewState(view), DEFAULT_VIEW_STATE).datasetId, mouse.datasetId);
  assert.deepEqual(parsePortableSession(encodeSession(view), view, view.buildHash).view, { ...view, selectedFeatureId: undefined });
  assert.throws(() => parsePortableSession(encodeSession(view), { ...view, datasetId: "human-gencode-v50" }, view.buildHash), /another annotation dataset/);
  assert.equal(datasetUrl("/api/v1/export?format=tsv", mouse.datasetId), "/api/v1/export?format=tsv&dataset=mouse-gencode-m39");
  assert.equal(datasetUrl("/reference/genome.fa", mouse.datasetId), "/reference/genome.fa?dataset=mouse-gencode-m39");
});

test("workspace storage isolates dataset and build without deleting legacy saved work", () => {
  const map = new Map<string, string>();
  const storage = { getItem: (key: string) => map.get(key) ?? null, setItem: (key: string, value: string) => { map.set(key, value); }, removeItem: (key: string) => { map.delete(key); } };
  const legacy = createEmptyWorkspaceState("legacy-build");
  saveWorkspaceState(storage, legacy);
  const migrated = loadWorkspaceState(storage, "legacy-build", "human-gencode-v45");
  assert.equal(migrated.status, "ready");
  assert.equal(migrated.state.datasetId, "human-gencode-v45");
  saveWorkspaceState(storage, migrated.state);
  saveWorkspaceState(storage, createEmptyWorkspaceState("mouse-build", mouse.datasetId));
  assert.equal(map.size, 3);
  assert.equal(loadWorkspaceState(storage, "other-build", mouse.datasetId).status, "missing");
  assert.equal(loadWorkspaceState(storage, "legacy-build", "human-gencode-v50").status, "missing");
  clearWorkspaceState(storage, "mouse-build", mouse.datasetId);
  assert.ok(map.has(WORKSPACE_STORAGE_KEY));
  assert.ok(map.has(workspaceStorageKey("legacy-build", "human-gencode-v45")));
});

test("switching datasets saves the current workspace and blocks pending annotation drafts", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const editor = readFileSync(new URL("../src/components/LocalAnnotationsEditor.tsx", import.meta.url), "utf8");
  const selector = readFileSync(new URL("../src/components/CommandBar.tsx", import.meta.url), "utf8");
  assert.match(selector, /aria-label="Genome annotation"/);
  assert.match(app, /data-unsaved-annotation/);
  assert.match(app, /saveWorkspaceState[\s\S]*window\.location\.assign/);
  assert.match(editor, /data-unsaved-annotation=/);
});
