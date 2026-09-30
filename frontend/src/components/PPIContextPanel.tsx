import { useEffect, useMemo, useState } from "react";
import { loadGenePPIContext } from "../api";
import { observePPIToken, type PPITokenObservation } from "../lib/ppiContext";
import { SOURCE_META, type BuildManifest, type GenePPIContext, type ProteinFeature, type Transcript } from "../types";

function Observation({ value, transcript, onInspectFeature }: {
  value: PPITokenObservation; transcript: Transcript; onInspectFeature: (feature: ProteinFeature) => void;
}) {
  return <td className={`ppi-observation ppi-observation-${value.state}`} title={value.reason}>
    <strong>{value.state === "observed" ? "Observed" : value.state === "not-observed" ? "Not observed" : "Not assessed"}</strong>
    {value.state === "observed" && <button type="button" onClick={() => onInspectFeature(value.calls[0])}
      aria-label={`Inspect ${value.token} in ${transcript.name}`}>{value.calls.length} call{value.calls.length === 1 ? "" : "s"}</button>}
    {value.state === "not-assessed" && <small>{value.reason}</small>}
  </td>;
}

function RequirementTable({ tokens, selected, comparison, manifest, onInspectFeature }: {
  tokens: string[]; selected: Transcript; comparison: Transcript; manifest: BuildManifest;
  onInspectFeature: (feature: ProteinFeature) => void;
}) {
  const [page, setPage] = useState(0);
  const unique = useMemo(() => [...new Set(tokens)].sort(), [tokens]);
  const lastPage = Math.max(0, Math.ceil(unique.length / 6) - 1), currentPage = Math.min(page, lastPage);
  if (!unique.length) return <p className="ppi-empty-requirements">No focal feature identifiers supplied for this evidence type.</p>;
  return <>
    <table className="ppi-requirements">
      <caption>Focal feature observations · aggregated identifiers, not paired mechanisms</caption>
      <thead><tr><th scope="col">Identifier</th><th scope="col">{selected.name}</th><th scope="col">{comparison.name}</th></tr></thead>
      <tbody>{unique.slice(currentPage * 6, currentPage * 6 + 6).map((token) => {
        const a = observePPIToken(token, selected, manifest), b = observePPIToken(token, comparison, manifest);
        return <tr key={token}>
          <th scope="row"><code>{token}</code><small>{a.source ? SOURCE_META[a.source].label : "Unmapped namespace"}</small></th>
          <Observation value={a} transcript={selected} onInspectFeature={onInspectFeature} />
          <Observation value={b} transcript={comparison} onInspectFeature={onInspectFeature} />
        </tr>;
      })}</tbody>
    </table>
    {lastPage > 0 && <nav className="feature-comparison-pagination" aria-label="Focal feature identifier pages">
      <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous identifiers</button>
      <span>{currentPage * 6 + 1}–{Math.min(unique.length, currentPage * 6 + 6)} of {unique.length}</span>
      <button type="button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next identifiers</button>
    </nav>}
  </>;
}

export function PPIContextPanel({ geneId, manifest, selectedTranscript, comparisonTranscript, onInspectFeature }: {
  geneId: string; manifest: BuildManifest; selectedTranscript: Transcript; comparisonTranscript: Transcript;
  onInspectFeature: (feature: ProteinFeature) => void;
}) {
  const [evidence, setEvidence] = useState<"all" | "feature-linked">("feature-linked");
  const [offset, setOffset] = useState(0), [retry, setRetry] = useState(0);
  const [state, setState] = useState<{ status: "loading" | "ready" | "error"; result?: GenePPIContext; error?: string }>({ status: "loading" });
  const applicable = manifest.species === "human";
  const installed = manifest.ppiContext?.status === "loaded" && manifest.capabilities.ppiContext === true;
  useEffect(() => {
    if (!applicable || !installed) return;
    const controller = new AbortController();
    setState({ status: "loading" });
    void loadGenePPIContext(geneId, manifest, offset, evidence, controller.signal)
      .then(result => { if (!controller.signal.aborted) setState({ status: "ready", result }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setState({ status: "error", error: error instanceof Error ? error.message : "Interaction context could not be loaded." }); });
    return () => controller.abort();
  }, [applicable, installed, manifest, geneId, offset, evidence, retry]);
  const result = state.result;
  return <section className="ppi-context-panel" aria-label="Human protein interaction context">
    <header>
      <span className="eyebrow">SpliceImpactR · human</span><h4>PPI context and focal feature evidence</h4>
      <p>Gene-level interaction records with features observed in each isoform. This is not a prediction of binding, affinity, or interaction gain/loss. Partner isoforms and expression are not assessed.</p>
    </header>
    {!applicable ? <p className="ppi-state" role="status">Not applicable: the available interaction resource is human-only. It is never applied to mouse.</p>
      : !installed ? <p className="ppi-state" role="status">{manifest.ppiContext?.reason ?? "The optional interaction context has not been prepared for this annotation build. See the README PPI-context setup instructions."}</p>
        : state.status === "loading" ? <p className="ppi-state" role="status">Loading local interaction context…</p>
          : state.status === "error" ? <div className="ppi-state" role="status"><p>{state.error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Retry interaction context</button></div>
            : result?.status !== "loaded" ? <p className="ppi-state" role="status">{result?.reason ?? "Interaction context unavailable."}</p>
              : <>
                <label className="ppi-evidence-filter">Interaction records
                  <select aria-label="Interaction records" value={evidence} onChange={(event) => { setEvidence(event.currentTarget.value as "all" | "feature-linked"); setOffset(0); }}>
                    <option value="feature-linked">Domain / motif linked</option><option value="all">All gene-level records</option>
                  </select>
                </label>
                <p className="ppi-record-counts">{result.counts?.records.toLocaleString()} matching resource records · {result.counts?.partnerGenes.toLocaleString()} partner genes · {result.counts?.allRecords.toLocaleString()} total gene records</p>
                {!result.records.length && <p className="ppi-state" role="status">No records in this resource match the selected evidence filter. This does not establish absence of biological interactions.</p>}
                <div className="ppi-records">
                  {result.records.map((record, index) => <details className="ppi-record" key={`${evidence}:${offset}:${record.recordId}`} open={index === 0}>
                    <summary><strong>{record.partner.symbol || record.partner.id}</strong><code>{record.partner.id}</code>
                      <span>{[record.biogrid ? "BioGRID" : "", record.ddi.flag ? "DDI" : "", record.dmi.flag ? "DMI" : ""].filter(Boolean).join(" · ")}</span>
                    </summary>
                    <div>
                      <p className="ppi-endpoint-note">Focal gene {geneId} is endpoint {record.focalEndpoint}.{record.selfInteraction ? " Self-interaction: both endpoint lists are retained." : " Only its own endpoint identifiers are assessed."}
                        {!record.partner.availableInDataset ? " Partner has no exact gene-ID match in this annotation dataset." : ""}</p>
                      {record.ddi.flag && <section><h5>Domain–domain context</h5>
                        <RequirementTable tokens={record.ddi.focalPfamAccessions} selected={selectedTranscript} comparison={comparisonTranscript} manifest={manifest} onInspectFeature={onInspectFeature} />
                        <details className="ppi-partner-tokens"><summary>Unassessed partner identifiers ({record.ddi.partnerPfamAccessions.length})</summary><p>{record.ddi.partnerPfamAccessions.join(", ") || "Not supplied"}</p></details>
                      </section>}
                      {record.dmi.flag && <section><h5>Domain–motif context</h5>
                        <RequirementTable tokens={record.dmi.focalTokens} selected={selectedTranscript} comparison={comparisonTranscript} manifest={manifest} onInspectFeature={onInspectFeature} />
                        <details className="ppi-partner-tokens"><summary>Unassessed partner identifiers ({record.dmi.partnerTokens.length})</summary><p>{record.dmi.partnerTokens.join(", ") || "Not supplied"}</p></details>
                      </section>}
                      {!record.ddi.flag && !record.dmi.flag && <p className="ppi-state">Gene-level network record only; no focal domain/motif mechanism was supplied.</p>}
                    </div>
                  </details>)}
                </div>
                <nav className="feature-comparison-pagination" aria-label="Interaction context pages">
                  <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 12))}>Previous partners</button>
                  <span>{result.records.length ? offset + 1 : 0}–{offset + result.records.length} of {result.counts?.records.toLocaleString()}</span>
                  <button type="button" disabled={!result.page.hasMore || result.page.nextOffset === null} onClick={() => { if (result.page.nextOffset !== null) setOffset(result.page.nextOffset); }}>Next partners</button>
                </nav>
                <details className="ppi-provenance"><summary>Interaction provenance and limitations</summary>
                  <p>{result.provenance?.source} · SpliceImpactR {result.provenance?.packageVersion}</p>
                  <p>Network date/release: not supplied by the resource. It is not asserted to be Ensembl-release-matched. The feature observations are from this exact local annotation build.</p>
                  <dl><dt>Resource SHA-256</dt><dd>{result.provenance?.dataSha256}</dd><dt>Context identity</dt><dd>{result.provenance?.contextHash}</dd><dt>Annotation build</dt><dd>{manifest.buildHash}</dd></dl>
                  <p>Endpoint feature lists are aggregated; original mechanism pairings cannot be reconstructed. An observed focal feature does not establish a functioning interaction.</p>
                </details>
              </>}
    <p className="ppi-prediction-boundary">Interaction-switch predictions are disabled: the published SpliceImpactR method has an unresolved endpoint-attribution issue. No probability or confidence score is inferred.</p>
  </section>;
}
