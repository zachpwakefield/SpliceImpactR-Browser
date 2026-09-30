import { useId, useMemo, useState } from "react";
import { buildFeatureComparison, FEATURE_DIFFERENCE_LABELS, filterFeatureComparison } from "../lib/featureComparison";
import type { ComparisonExportFormat } from "../lib/comparisonExport";
import { SOURCE_META, type BuildManifest, type FeatureSource, type ProteinFeature, type Transcript } from "../types";

const ROWS_PER_PAGE = 12;
const CALLS_PER_PAGE = 6;

function CallList({ calls, transcript, onInspectFeature }: {
  calls: readonly ProteinFeature[];
  transcript: Transcript;
  onInspectFeature?: (feature: ProteinFeature) => void;
}) {
  const [page, setPage] = useState(0);
  if (!calls.length) return <p className="feature-comparison-absence">No call observed in this source</p>;
  const lastPage = Math.max(0, Math.ceil(calls.length / CALLS_PER_PAGE) - 1);
  const currentPage = Math.min(page, lastPage);
  const start = currentPage * CALLS_PER_PAGE;
  return <>
    <ul className="feature-comparison-calls">
      {calls.slice(start, start + CALLS_PER_PAGE).map((call) => {
        const aaOnly = call.projectionStatus !== undefined && call.projectionStatus !== "exact";
        const outsideProtein = call.aaEnd > transcript.proteinLength;
        const label = `Inspect ${SOURCE_META[call.source].label} ${call.featureId}, aa ${call.aaStart}–${call.aaEnd}, in ${transcript.name}`;
        return <li key={call.recordId}>
          {onInspectFeature ? <button type="button" onClick={() => onInspectFeature(call)} aria-label={label}
            title={`${call.name} · ${call.method} · ${call.recordId}`}>
            aa {call.aaStart.toLocaleString()}–{call.aaEnd.toLocaleString()}
          </button> : <span>aa {call.aaStart.toLocaleString()}–{call.aaEnd.toLocaleString()}</span>}
          {aaOnly && <small title={call.mappingReason}>AA only · {call.projectionStatus}</small>}
          {outsideProtein && <small>Outside stored protein bounds</small>}
        </li>;
      })}
    </ul>
    {lastPage > 0 && <div className="feature-comparison-call-pages" aria-label={`Call pages for ${transcript.name}`}>
      <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous calls</button>
      <span>{start + 1}–{Math.min(calls.length, start + CALLS_PER_PAGE)} of {calls.length}</span>
      <button type="button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next calls</button>
    </div>}
  </>;
}

export function FeatureComparisonPanel({ selectedTranscript, comparisonTranscript, sources, availability, onInspectFeature, onRetry, onExport }: {
  selectedTranscript: Transcript;
  comparisonTranscript: Transcript;
  sources: readonly FeatureSource[];
  availability?: BuildManifest["featureAvailability"];
  onInspectFeature?: (feature: ProteinFeature) => void;
  onRetry?: () => void;
  onExport?: (format: ComparisonExportFormat) => void;
}) {
  const headingId = useId(), queryId = useId();
  const [query, setQuery] = useState("");
  const [differencesOnly, setDifferencesOnly] = useState(true);
  const [page, setPage] = useState(0);
  const model = useMemo(() => buildFeatureComparison(selectedTranscript, comparisonTranscript, sources, availability),
    [selectedTranscript, comparisonTranscript, sources, availability]);
  const filtered = useMemo(() => filterFeatureComparison(model.rows, query, differencesOnly), [model.rows, query, differencesOnly]);
  const differentCount = model.rows.filter((row) => row.difference !== "same" && row.difference !== "unidentified").length;
  const sameCount = model.rows.filter((row) => row.difference === "same").length;
  const unidentifiedCount = model.rows.filter((row) => row.difference === "unidentified").length;
  const lastPage = Math.max(0, Math.ceil(filtered.length / ROWS_PER_PAGE) - 1), currentPage = Math.min(page, lastPage);
  const start = currentPage * ROWS_PER_PAGE;
  return <section className="feature-comparison" aria-labelledby={headingId} data-state={model.state}>
    <header>
      <span className="eyebrow">Protein annotations</span>
      <h4 id={headingId}>Actual protein-feature differences</h4>
      <p>Source + accession + method are compared. Amino-acid ranges are 1-based inclusive on each protein, not aligned residues. One-sided calls do not prove biological gain or loss.</p>
      <small>All available sources are included; Canvas source/class filters do not hide comparison evidence.</small>
    </header>
    {model.unavailableSources.length > 0 && <div className="feature-comparison-unavailable" role="note">
      <strong>Not compared: unavailable sources</strong>
      <ul>{model.unavailableSources.map(({ source, reason }) => <li key={source}>{SOURCE_META[source].label}{reason ? ` — ${reason}` : ""}</li>)}</ul>
    </div>}
    {model.state !== "ready" ? <div className="inspector-callout neutral" role="status">
      <p>{model.reason}</p>
      {model.state === "error" && onRetry && <button type="button" onClick={onRetry}>Retry both feature requests</button>}
    </div> : <>
      <div className="feature-comparison-summary" aria-label="Protein-feature comparison counts">
        <span><strong>{differentCount}</strong> different</span>
        <span><strong>{sameCount}</strong> same</span>
        <span><strong>{model.rows.length}</strong> feature identities</span>
        {unidentifiedCount > 0 && <span><strong>{unidentifiedCount}</strong> unidentified calls</span>}
      </div>
      <div className="feature-comparison-controls">
        <label htmlFor={queryId}>Find feature name or accession</label>
        <input id={queryId} type="search" maxLength={200} value={query} placeholder="e.g. zinc finger, IPR013087"
          onChange={(event) => { setQuery(event.currentTarget.value); setPage(0); }} />
        <label className="feature-comparison-checkbox"><input type="checkbox" checked={differencesOnly}
          onChange={(event) => { setDifferencesOnly(event.currentTarget.checked); setPage(0); }} />Show differences only</label>
      </div>
      {!filtered.length && <p className="feature-comparison-empty" role="status">{!model.rows.length
        ? "No feature calls were observed in the available sources for either protein."
        : query ? "No feature identities match this search."
          : "No recorded call differences in the available sources. Turn off “Show differences only” to inspect shared calls."}</p>}
      <div className="feature-comparison-rows">
        {filtered.slice(start, start + ROWS_PER_PAGE).map((row) => <article key={`${selectedTranscript.id}:${comparisonTranscript.id}:${row.key}`}
          className={`feature-difference-row feature-difference-${row.difference}`} data-difference={row.difference}>
          <header>
            <span className="feature-source-label" style={{ borderColor: SOURCE_META[row.source].color }}>{SOURCE_META[row.source].label}</span>
            <code>{row.difference === "unidentified" ? "Accession not provided" : row.accession}</code>
            <strong className="feature-difference-status">{FEATURE_DIFFERENCE_LABELS[row.difference]}</strong>
          </header>
          <h5>{row.names.join(" / ")}</h5>
          <small className="feature-comparison-method">{row.method || "Method not provided"}</small>
          <div className="feature-comparison-pair">
            <section aria-label={`Selected ${selectedTranscript.name} calls for ${row.accession}`}>
              <h6>Selected · {selectedTranscript.name}</h6><small>{row.selected.length} call{row.selected.length === 1 ? "" : "s"}</small>
              <CallList calls={row.selected} transcript={selectedTranscript} onInspectFeature={onInspectFeature} />
            </section>
            <section aria-label={`Comparison ${comparisonTranscript.name} calls for ${row.accession}`}>
              <h6>Comparison · {comparisonTranscript.name}</h6><small>{row.comparison.length} call{row.comparison.length === 1 ? "" : "s"}</small>
              <CallList calls={row.comparison} transcript={comparisonTranscript} onInspectFeature={onInspectFeature} />
            </section>
          </div>
        </article>)}
      </div>
      {lastPage > 0 && <nav className="feature-comparison-pagination" aria-label="Protein-feature comparison pages">
        <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous features</button>
        <span>{start + 1}–{Math.min(filtered.length, start + ROWS_PER_PAGE)} of {filtered.length}</span>
        <button type="button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next features</button>
      </nav>}
      {onExport && <div className="feature-comparison-export" role="group" aria-label="Export complete protein-feature comparison">
        <button type="button" onClick={() => onExport("csv")}>Feature calls CSV</button>
        <button type="button" onClick={() => onExport("tsv")}>Feature calls TSV</button>
        <small>Exports every compared call, including shared calls and all pages. Search/display filters are not applied.</small>
      </div>}
    </>}
  </section>;
}
