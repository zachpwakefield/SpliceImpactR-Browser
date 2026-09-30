import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CommandBar } from "../src/components/CommandBar";
import { DEFAULT_VIEW_STATE, FALLBACK_MANIFEST } from "../src/data/sp1";
import { APPLICATION_FILE_PREFIX, APPLICATION_MARK, APPLICATION_NAME, applicationDocumentTitle } from "../src/lib/application";
import { SESSION_FORMAT, encodeSession, parsePortableSession } from "../src/lib/session";
import { WORKSPACE_STORAGE_KEY } from "../src/lib/workspaceStore";

test("application branding and document titles follow the selected annotation", () => {
  assert.equal(APPLICATION_NAME, "SpliceImpactR Browser");
  assert.equal(APPLICATION_MARK, "SB");
  assert.equal(APPLICATION_FILE_PREFIX, "spliceimpactr-browser");
  assert.equal(applicationDocumentTitle(), APPLICATION_NAME);
  assert.equal(applicationDocumentTitle("Sp1", "GENCODE M39 · Ensembl 116"),
    "Sp1 · SpliceImpactR Browser · GENCODE M39 · Ensembl 116");
  assert.doesNotMatch(applicationDocumentTitle("Sp1", "GENCODE M39"), /v45/);
});

test("the rendered command bar uses the new product name and mark", () => {
  const noop = () => undefined;
  const html = renderToStaticMarkup(createElement(CommandBar, {
    manifest: FALLBACK_MANIFEST, manifestState: "ready", query: "SP1",
    locus: DEFAULT_VIEW_STATE.locus, displayMode: "auto", effectiveDisplayMode: "expanded",
    inspectorOpen: true, searchResults: [], searchState: "idle", canFitTranscript: true,
    onQueryChange: noop, onSubmit: noop, onFitGene: noop, onFitTranscript: noop,
    onZoom: noop, onDisplayModeChange: noop, onToggleInspector: noop, onToggleHelp: noop,
  }));
  assert.match(html, /<strong>SpliceImpactR Browser<\/strong>/);
  assert.match(html, /class="brand-mark"[^>]*>SB<\/span>/);
  assert.doesNotMatch(html, /Transcript browser|>TB<\/span>/);
});

test("the initial HTML and favicon have no stale product or fixed-release title", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const icon = readFileSync(new URL("../public/favicon.svg", import.meta.url), "utf8");
  assert.match(html, /<title>SpliceImpactR Browser<\/title>/);
  assert.match(html, /href="\/favicon.svg"/);
  assert.doesNotMatch(html, /Local Transcript Browser|GENCODE v45/);
  assert.match(icon, /aria-label="SpliceImpactR Browser"/);
  assert.match(icon, />SB<\/text>/);
});

test("the display-name change keeps existing session and workspace identities", () => {
  assert.equal(SESSION_FORMAT, "local-transcript-browser-session");
  assert.equal(WORKSPACE_STORAGE_KEY, "transcript-browser:workspace:v1");
  const oldSession = encodeSession(DEFAULT_VIEW_STATE);
  assert.equal(JSON.parse(oldSession).format, SESSION_FORMAT);
  assert.equal(parsePortableSession(oldSession, DEFAULT_VIEW_STATE, DEFAULT_VIEW_STATE.buildHash).view.selectedGeneId,
    DEFAULT_VIEW_STATE.selectedGeneId);
});
