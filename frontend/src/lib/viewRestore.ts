import type { BrowserViewState, BuildManifest } from "../types";
import { DEFAULT_VIEW_STATE } from "../data/sp1";
import { hasExplicitViewState } from "./urlState";
import type { LocalWorkspaceState } from "./workspaceStore";

export interface InitialViewChoice {
  view: BrowserViewState;
  restoredLastView: boolean;
}

/** Only a legacy human-v45 package may use the historical SP1 starting view. */
export function manifestDefaultView(manifest: BuildManifest): BrowserViewState {
  const view = manifest.defaultView;
  if (!view && (manifest.species === "mouse" || (manifest.datasetId && manifest.datasetId !== "human-gencode-v45"))) {
    throw new Error("The selected dataset has no validated starting gene or locus.");
  }
  if (view && (!view.selectedGeneId || !view.locus.chrom || !Number.isSafeInteger(view.locus.start0)
    || !Number.isSafeInteger(view.locus.end0) || view.locus.start0 < 0 || view.locus.end0 <= view.locus.start0)) {
    throw new Error("The selected dataset's starting view is invalid.");
  }
  return {
    ...DEFAULT_VIEW_STATE,
    ...(view ?? {}),
    datasetId: manifest.datasetId ?? "human-gencode-v45",
    buildHash: manifest.buildHash,
    expandedTranscriptIds: view?.expandedTranscriptIds ?? (view ? [] : DEFAULT_VIEW_STATE.expandedTranscriptIds),
    comparisonTranscriptId: "",
    transcriptOrderIds: [],
    pinnedTranscriptIds: [],
    activeSources: manifest.featureSources,
  };
}

/** Explicit URLs always win; automatic restoration is limited to an empty view URL. */
export function chooseInitialView(
  search: string,
  urlView: BrowserViewState,
  workspace: LocalWorkspaceState,
): InitialViewChoice {
  if (!hasExplicitViewState(search) && workspace.restoreLastView && workspace.lastView) {
    return { view: workspace.lastView, restoredLastView: true };
  }
  return { view: urlView, restoredLastView: false };
}
