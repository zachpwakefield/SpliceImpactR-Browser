import type { BuildManifest, FeatureSource, ProteinFeature, Transcript } from "../types";

export interface PPITokenObservation {
  token: string;
  source?: FeatureSource;
  state: "observed" | "not-observed" | "not-assessed";
  reason?: string;
  calls: ProteinFeature[];
}

/** Identify only declared identifier namespaces, never guess SMART/CDD or translate between sources. */
export function ppiTokenSource(token: string): FeatureSource | undefined {
  if (/^PF\d{5}(?:\.\d+)?$/u.test(token)) return "pfam";
  if (/^IPR\d{6}$/u.test(token)) return "interpro";
  if (/^(?:LIG|MOD|DOC|DEG|TRG|CLV)_[A-Za-z0-9_-]+$/u.test(token)) return "elm";
  return undefined;
}

/** Focal annotation observations only. Aggregated endpoint lists cannot define paired mechanisms or interaction switches. */
export function observePPIToken(token: string, transcript: Transcript, manifest: BuildManifest): PPITokenObservation {
  const source = ppiTokenSource(token);
  const base = { token, source, calls: [] };
  if (manifest.species !== "human") return { ...base, state: "not-assessed", reason: "The available interaction resource is human-only." };
  if (!source) return { ...base, state: "not-assessed", reason: "Identifier namespace not supported by the available feature sources." };
  if (transcript.proteinLength <= 0) return { ...base, state: "not-assessed", reason: "No local translated product." };
  if (!manifest.featureSources.includes(source) || manifest.featureAvailability?.[source]?.status === "unavailable") {
    return { ...base, state: "not-assessed", reason: manifest.featureAvailability?.[source]?.reason ?? "This annotation source is unavailable." };
  }
  if (transcript.featuresState !== "ready") return { ...base, state: "not-assessed",
    reason: transcript.featuresState === "error" ? "Protein-feature loading failed." : "Protein-feature calls have not finished loading." };
  const calls = transcript.features.filter((call) => call.source === source && call.featureId === token);
  if (calls.some((call) => call.transcriptId !== transcript.id)) return { ...base, state: "not-assessed", reason: "Feature transcript ownership is invalid." };
  if (calls.some((call) => !Number.isInteger(call.aaStart) || !Number.isInteger(call.aaEnd)
    || call.aaStart < 1 || call.aaEnd < call.aaStart || call.aaEnd > transcript.proteinLength)) {
    return { ...base, state: "not-assessed", reason: "A recorded call has invalid or out-of-protein amino-acid bounds; it remains available as an annotation audit, not protein evidence." };
  }
  return { token, source, calls, state: calls.length ? "observed" : "not-observed" };
}
