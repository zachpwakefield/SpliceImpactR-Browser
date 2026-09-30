import {
  FEATURE_SOURCES,
  type BuildManifest,
  type FeatureSource,
  type ProteinFeature,
  type Transcript,
} from "../types";

export type FeatureDifference = "selected-only" | "comparison-only" | "call-count-diff" | "intervals-diff" | "same" | "unidentified";
export const FEATURE_DIFFERENCE_LABELS: Record<FeatureDifference, string> = {
  "selected-only": "Observed only on selected",
  "comparison-only": "Observed only on comparison",
  "call-count-diff": "Call count differs",
  "intervals-diff": "AA coordinates differ",
  same: "Same recorded calls",
  unidentified: "Accession unavailable · not matched",
};

export interface FeatureComparisonRow {
  key: string;
  source: FeatureSource;
  accession: string;
  method: string;
  names: string[];
  selected: ProteinFeature[];
  comparison: ProteinFeature[];
  difference: FeatureDifference;
}

export interface FeatureComparisonModel {
  state: "ready" | "not-loaded" | "error" | "not-applicable" | "invalid";
  reason?: string;
  rows: FeatureComparisonRow[];
  unavailableSources: { source: FeatureSource; reason?: string }[];
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function sortedCalls(calls: readonly ProteinFeature[]): ProteinFeature[] {
  return [...calls].sort((a, b) => a.aaStart - b.aaStart || a.aaEnd - b.aaEnd || compareText(a.recordId, b.recordId));
}

/**
 * Compare source observations, not homologous residues or biological loss/gain.
 * Record IDs are transcript-specific. Repeated calls are multisets; we never
 * invent a one-to-one match, collapse accessions, or equate different sources.
 */
export function buildFeatureComparison(
  selected: Transcript,
  comparison: Transcript,
  sources: readonly FeatureSource[] = FEATURE_SOURCES,
  availability?: BuildManifest["featureAvailability"],
): FeatureComparisonModel {
  const unavailableSources = [...new Set(sources)].flatMap((source) => availability?.[source]?.status === "unavailable"
    ? [{ source, reason: availability[source]?.reason }]
    : []);
  const base = { rows: [], unavailableSources };
  if (selected.id === comparison.id || (selected.geneId && comparison.geneId && selected.geneId !== comparison.geneId)) {
    return { ...base, state: "invalid", reason: "Choose two different transcripts from the same gene." };
  }
  if (selected.proteinLength <= 0 || comparison.proteinLength <= 0) {
    return { ...base, state: "not-applicable", reason: "Both transcripts need a local translated product for a protein-feature comparison. A missing product is not an empty feature result." };
  }
  if (selected.featuresState === "error" || comparison.featuresState === "error") {
    return { ...base, state: "error", reason: "One or both protein-feature requests failed. No differences are inferred from missing responses." };
  }
  if (selected.featuresState !== "ready" || comparison.featuresState !== "ready") {
    return { ...base, state: "not-loaded", reason: "Loading protein-feature calls for both transcripts…" };
  }
  const available = new Set(sources.filter((source) => availability?.[source]?.status !== "unavailable"));
  const groups = new Map<string, Omit<FeatureComparisonRow, "difference">>();
  for (const [role, transcript] of [["selected", selected], ["comparison", comparison]] as const) {
    for (const feature of transcript.features) {
      if (!available.has(feature.source)) continue;
      if (feature.transcriptId !== transcript.id || !Number.isInteger(feature.aaStart)
        || !Number.isInteger(feature.aaEnd) || feature.aaStart < 1 || feature.aaEnd < feature.aaStart) {
        return { ...base, state: "invalid", reason: "A feature has mismatched transcript ownership or invalid amino-acid bounds. Comparison was stopped." };
      }
      const identified = Boolean(feature.featureId.trim() && feature.featureId !== "local-record");
      const key = JSON.stringify([feature.source, feature.featureId, feature.method,
        ...(identified ? [] : [feature.transcriptId, feature.recordId])]);
      let group = groups.get(key);
      if (!group) {
        group = { key, source: feature.source, accession: feature.featureId, method: feature.method, names: [], selected: [], comparison: [] };
        groups.set(key, group);
      }
      if (!group.names.includes(feature.name)) group.names.push(feature.name);
      group[role].push(feature);
    }
  }
  const rows = [...groups.values()].map((group): FeatureComparisonRow => {
    const selectedCalls = sortedCalls(group.selected), comparisonCalls = sortedCalls(group.comparison);
    const identified = Boolean(group.accession.trim() && group.accession !== "local-record");
    const difference: FeatureDifference = !identified ? "unidentified"
      : !selectedCalls.length ? "comparison-only"
      : !comparisonCalls.length ? "selected-only"
      : selectedCalls.length !== comparisonCalls.length ? "call-count-diff"
      : selectedCalls.some((call, index) => call.aaStart !== comparisonCalls[index].aaStart || call.aaEnd !== comparisonCalls[index].aaEnd)
        ? "intervals-diff" : "same";
    return { ...group, names: [...group.names].sort(compareText), selected: selectedCalls, comparison: comparisonCalls, difference };
  }).sort((a, b) => FEATURE_SOURCES.indexOf(a.source) - FEATURE_SOURCES.indexOf(b.source)
    || compareText(a.accession, b.accession) || compareText(a.method, b.method));
  return { state: "ready", rows, unavailableSources };
}

export function filterFeatureComparison(
  rows: readonly FeatureComparisonRow[],
  query: string,
  differencesOnly: boolean,
): FeatureComparisonRow[] {
  const search = query.trim().toLocaleLowerCase("en-US");
  return rows.filter((row) => (!differencesOnly || row.difference !== "same") && (!search
    || [row.source, row.accession, row.method, ...row.names].join(" ").toLocaleLowerCase("en-US").includes(search)));
}
