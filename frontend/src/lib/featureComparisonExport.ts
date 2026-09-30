import { protectSpreadsheetUserValue, quoteDelimitedField, type ComparisonExportFormat } from "./comparisonExport";
import type { FeatureComparisonModel } from "./featureComparison";
import type { BuildManifest, ProteinFeature, Transcript } from "../types";

export const FEATURE_COMPARISON_EXPORT_COLUMNS = [
  "record_type", "dataset_id", "build_hash", "species", "gencode_release", "ensembl_release", "assembly",
  "selected_transcript", "comparison_transcript", "coordinate_contract", "source_availability_json",
  "selected_protein", "selected_protein_length", "comparison_protein", "comparison_protein_length",
  "source", "accession", "method", "difference", "selected_calls_json", "comparison_calls_json",
] as const;

function exportedCalls(calls: readonly ProteinFeature[], transcript: Transcript) {
  return calls.map((call) => ({ recordId: call.recordId, transcriptId: call.transcriptId,
    name: call.name, aaStart: call.aaStart, aaEnd: call.aaEnd,
    projectionStatus: call.projectionStatus ?? "not declared", mappingReason: call.mappingReason ?? null,
    outsideStoredProteinBounds: call.aaEnd > transcript.proteinLength }));
}

/** One explicit provenance row plus one row per identity; no invented feature in an empty comparison. */
export function serializeFeatureComparison(
  model: FeatureComparisonModel,
  selected: Transcript,
  comparison: Transcript,
  manifest: BuildManifest,
  format: ComparisonExportFormat,
): string {
  if (model.state !== "ready") throw new Error("Both protein-feature lists must be loaded before export.");
  const delimiter = format === "csv" ? "," : "\t";
  const provenance = [manifest.datasetId ?? "not declared", manifest.buildHash, manifest.species ?? "not declared",
    manifest.gencodeRelease ?? manifest.release, manifest.ensemblRelease ?? "not declared", manifest.assembly,
    selected.versionedId, comparison.versionedId, "amino acids: 1-based inclusive; no sequence alignment",
    JSON.stringify(manifest.featureAvailability ?? {}), selected.versionedProteinId || selected.proteinId,
    selected.proteinLength, comparison.versionedProteinId || comparison.proteinId, comparison.proteinLength];
  const empty = ["", "", "", "", "", ""];
  const rows = [["provenance", ...provenance, ...empty], ...model.rows.map((row) => ["feature_identity", ...provenance,
    row.source, row.accession, row.method, row.difference,
    JSON.stringify(exportedCalls(row.selected, selected)), JSON.stringify(exportedCalls(row.comparison, comparison))])];
  return [FEATURE_COMPARISON_EXPORT_COLUMNS.join(delimiter), ...rows.map((row) => row.map((value) =>
    quoteDelimitedField(typeof value === "string" ? protectSpreadsheetUserValue(value) : value, delimiter)).join(delimiter))].join("\n") + "\n";
}
