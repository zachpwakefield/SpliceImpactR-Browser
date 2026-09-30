import {
  FEATURE_CLASSES,
  FEATURE_SOURCES,
  TRANSCRIPT_FLAGS,
  type BrowserViewState,
  type DisplayModeSetting,
  type FeatureClass,
  type FeatureSource,
  type InspectorTab,
  type RowDensity,
  type TranscriptFlag,
} from "../types";
import { formatLocus, parseLocus } from "./coordinates";
import { MAX_COLLAPSED_PROTEIN_TRANSCRIPTS, MAX_EXPANDED_TRANSCRIPTS } from "./navigation";
import { highlightKey, parseHighlightInput } from "./eventHighlights";

const TABS: InspectorTab[] = ["gene", "transcript", "compare", "feature", "sequence", "table"];
const MODES: DisplayModeSetting[] = ["auto", "overview", "compact", "labeled", "expanded"];
const DENSITIES: RowDensity[] = ["compact", "comfortable"];
const EXPLICIT_VIEW_KEYS = new Set([
  "build", "gene", "locus", "tx", "compareTx", "txOrder", "expanded", "pinned",
  "allProteins", "collapsedProteins",
  "sources", "classes", "excludeBiotypes", "flags", "density", "canvasKeys", "tab", "mode", "feature",
  "hi",
]);

export function hasExplicitViewState(search: string): boolean {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return [...params.keys()].some((key) => EXPLICIT_VIEW_KEYS.has(key));
}

function commaValues(value: string | null): string[] {
  return value ? value.split(",").map((item) => item.trim()).filter(Boolean) : [];
}

function transcriptOrderValues(value: string | null, maximum = 500): string[] {
  const seen = new Set<string>();
  return commaValues(value)
    .filter((id) => id.length <= 80 && /^[A-Za-z0-9_.:-]+$/u.test(id))
    .filter((id) => {
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    })
    .slice(0, maximum);
}

export function parseViewState(search: string, fallback: BrowserViewState): BrowserViewState {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const locus = parseLocus(params.get("locus") ?? "") ?? fallback.locus;
  const sourceValues = commaValues(params.get("sources")).filter(
    (value): value is FeatureSource => FEATURE_SOURCES.includes(value as FeatureSource),
  );
  const classValues = commaValues(params.get("classes")).filter(
    (value): value is FeatureClass => FEATURE_CLASSES.includes(value as FeatureClass),
  );
  const flagValues = commaValues(params.get("flags")).filter(
    (value): value is TranscriptFlag => TRANSCRIPT_FLAGS.includes(value as TranscriptFlag),
  );
  const excludedBiotypes = commaValues(params.get("excludeBiotypes"))
    .filter((value) => value.length <= 80 && /^[\w.:-]+$/u.test(value));
  const tabValue = params.get("tab") as InspectorTab | null;
  const modeValue = params.get("mode") as DisplayModeSetting | null;
  const densityValue = params.get("density") as RowDensity | null;
  const canvasKeys = params.get("canvasKeys");
  let genomicHighlights = fallback.genomicHighlights;
  if (params.has("hi")) {
    try { genomicHighlights = params.get("hi") ? parseHighlightInput(params.get("hi")!) : []; }
    catch { genomicHighlights = []; } // Untrusted URLs never create partial or unbounded event lists.
  }
  const expandedTranscriptIds = params.has("expanded")
    ? transcriptOrderValues(params.get("expanded"), MAX_EXPANDED_TRANSCRIPTS)
    : fallback.expandedTranscriptIds;
  // An old, explicitly encoded view has its own disclosure state. It must not
  // acquire a saved All preference from the fallback used to read that URL.
  const legacyExpansion = !params.has("allProteins")
    && (params.has("expanded") || params.has("mode"));
  const expandAllProteins = params.has("allProteins")
    ? params.get("allProteins") === "1"
    : legacyExpansion && fallback.expandAllProteins !== undefined
      ? false
      : fallback.expandAllProteins;
  const collapsedProteinTranscriptIds = params.has("collapsedProteins")
    ? transcriptOrderValues(params.get("collapsedProteins"), MAX_COLLAPSED_PROTEIN_TRANSCRIPTS)
    : legacyExpansion && fallback.collapsedProteinTranscriptIds !== undefined
      ? []
      : fallback.collapsedProteinTranscriptIds;
  return {
    ...(params.get("dataset") || fallback.datasetId ? { datasetId: params.get("dataset") || fallback.datasetId } : {}),
    buildHash: params.get("build") || fallback.buildHash,
    selectedGeneId: params.get("gene") || fallback.selectedGeneId,
    locus,
    selectedTranscriptId: params.get("tx") || fallback.selectedTranscriptId,
    comparisonTranscriptId: params.has("compareTx")
      ? (params.get("compareTx") || "")
      : fallback.comparisonTranscriptId,
    transcriptOrderIds: params.has("txOrder")
      ? transcriptOrderValues(params.get("txOrder"))
      : fallback.transcriptOrderIds,
    expandedTranscriptIds,
    ...(expandAllProteins !== undefined ? { expandAllProteins } : {}),
    ...(collapsedProteinTranscriptIds !== undefined ? {
      collapsedProteinTranscriptIds: collapsedProteinTranscriptIds.filter((id) => !expandedTranscriptIds.includes(id)),
    } : {}),
    pinnedTranscriptIds: params.has("pinned")
      ? commaValues(params.get("pinned"))
      : fallback.pinnedTranscriptIds,
    activeSources: params.has("sources") ? sourceValues : fallback.activeSources,
    activeFeatureClasses: params.has("classes") ? classValues : fallback.activeFeatureClasses,
    excludedTranscriptBiotypes: params.has("excludeBiotypes")
      ? excludedBiotypes
      : fallback.excludedTranscriptBiotypes,
    activeTranscriptFlags: params.has("flags") ? flagValues : fallback.activeTranscriptFlags,
    rowDensity: densityValue && DENSITIES.includes(densityValue) ? densityValue : fallback.rowDensity,
    canvasKeyboardShortcuts: canvasKeys === "0"
      ? false
      : canvasKeys === "1"
        ? true
        : fallback.canvasKeyboardShortcuts,
    inspectorTab: tabValue && TABS.includes(tabValue) ? tabValue : fallback.inspectorTab,
    selectedFeatureId: params.get("feature") || undefined,
    displayMode: modeValue && MODES.includes(modeValue) ? modeValue : fallback.displayMode,
    ...(genomicHighlights !== undefined ? { genomicHighlights } : {}),
  };
}

export function encodeViewState(state: BrowserViewState): string {
  const params = new URLSearchParams();
  if (state.datasetId) params.set("dataset", state.datasetId);
  params.set("build", state.buildHash);
  params.set("gene", state.selectedGeneId);
  params.set("locus", formatLocus(state.locus).replaceAll(",", ""));
  params.set("tx", state.selectedTranscriptId);
  if (state.comparisonTranscriptId) params.set("compareTx", state.comparisonTranscriptId);
  params.set("txOrder", state.transcriptOrderIds.join(","));
  params.set("expanded", state.expandedTranscriptIds.join(","));
  if (state.expandAllProteins !== undefined) params.set("allProteins", state.expandAllProteins ? "1" : "0");
  if (state.collapsedProteinTranscriptIds !== undefined) {
    params.set("collapsedProteins", state.collapsedProteinTranscriptIds.join(","));
  }
  params.set("pinned", state.pinnedTranscriptIds.join(","));
  params.set("sources", state.activeSources.join(","));
  params.set("classes", state.activeFeatureClasses.join(","));
  params.set("excludeBiotypes", state.excludedTranscriptBiotypes.join(","));
  params.set("flags", state.activeTranscriptFlags.join(","));
  params.set("density", state.rowDensity);
  params.set("canvasKeys", state.canvasKeyboardShortcuts ? "1" : "0");
  params.set("tab", state.inspectorTab);
  params.set("mode", state.displayMode);
  if (state.selectedFeatureId) params.set("feature", state.selectedFeatureId);
  if (state.genomicHighlights !== undefined) params.set("hi", state.genomicHighlights.map(highlightKey).join(";"));
  return `?${params.toString()}`;
}

export function requestedBuildHash(search: string): string | null {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return params.get("build");
}

export function restoreViewState(
  search: string,
  fallback: BrowserViewState,
  currentBuildHash: string,
): { view: BrowserViewState; mismatchedBuild?: string } {
  const requested = requestedBuildHash(search);
  if (requested && requested !== currentBuildHash) {
    return {
      view: { ...fallback, buildHash: currentBuildHash },
      mismatchedBuild: requested,
    };
  }
  return {
    view: {
      ...parseViewState(search, { ...fallback, buildHash: currentBuildHash }),
      buildHash: currentBuildHash,
    },
  };
}
