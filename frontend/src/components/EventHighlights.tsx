import { useId, useState, type FormEvent } from "react";
import { MAX_LOCUS_SPAN_BP } from "../lib/coordinates";
import {
  checkHighlightBounds, highlightColor, highlightKey, MAX_EVENT_HIGHLIGHTS,
  MAX_HIGHLIGHT_INPUT_CHARACTERS, parseHighlightInput, projectGenomicEvent, validateHighlights,
} from "../lib/eventHighlights";
import type { Gene, Locus, Transcript } from "../types";

interface Props {
  highlights: readonly Locus[];
  chromosomeLengths?: Record<string, number>;
  gene: Gene;
  selected?: Transcript;
  comparison?: Transcript;
  onChange: (highlights: Locus[]) => void;
  onNavigate: (locus: Locus) => void;
}

function ranges(values: readonly { start1: number; end1: number }[]): string {
  return values.map((range) => range.start1 === range.end1 ? String(range.start1) : `${range.start1}–${range.end1}`).join(", ");
}

export function EventHighlights({ highlights, chromosomeLengths, gene, selected, comparison, onChange, onNavigate }: Props) {
  const id = useId();
  const [input, setInput] = useState("");
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const sameChrom = highlights.filter((interval) => interval.chrom === gene.chrom);
  const union = sameChrom.length ? {
    chrom: gene.chrom, start0: Math.min(...sameChrom.map((interval) => interval.start0)),
    end0: Math.max(...sameChrom.map((interval) => interval.end0)),
  } : undefined;
  const canFit = union && union.end0 - union.start0 <= MAX_LOCUS_SPAN_BP;
  function navigate(interval: Locus) {
    const padding = Math.min(Math.max(40, Math.round((interval.end0 - interval.start0) * 0.08)),
      Math.floor((MAX_LOCUS_SPAN_BP - (interval.end0 - interval.start0)) / 2));
    const length = chromosomeLengths?.[interval.chrom] ?? interval.end0;
    onNavigate({ chrom: interval.chrom, start0: Math.max(0, interval.start0 - padding), end0: Math.min(length, interval.end0 + padding) });
  }
  function add(event: FormEvent) {
    event.preventDefault();
    try {
      const added = parseHighlightInput(input, gene.chrom);
      checkHighlightBounds(added, chromosomeLengths);
      const next = validateHighlights([...new Map([...highlights, ...added].map((interval) => [highlightKey(interval), interval])).values()]);
      onChange(next);
      setMessage(`${next.length} genomic event highlight${next.length === 1 ? "" : "s"}. Gene and viewport unchanged.`);
      setInput(""); setError(undefined);
    } catch (error) { setError(error instanceof Error ? error.message : "Invalid genomic intervals."); setMessage(undefined); }
  }
  return <details className="event-highlights">
    <summary><span className="event-mark" aria-hidden="true">▧</span> Event highlights <span className="event-count">{highlights.length}</span>
      <small>User genomic intervals · transcript + protein projection</small></summary>
    <div className="event-editor">
      <form onSubmit={add}>
        <label htmlFor={id}>Genomic intervals</label>
        <textarea id={id} value={input} maxLength={MAX_HIGHLIGHT_INPUT_CHARACTERS} rows={2}
          placeholder={`${gene.chrom}:1-3,5-9,22-50`}
          aria-describedby={`${id}-help`} aria-invalid={Boolean(error)}
          onChange={(event) => { setInput(event.target.value); setError(undefined); }} />
        <p id={`${id}-help`}>1-based inclusive. Commas separate ranges on one chromosome; use a new line for another chromosome.
          Thousands commas are supported for one complete interval per line. Up to {MAX_EVENT_HIGHLIGHTS} intervals.</p>
        <div className="event-actions"><button type="submit" disabled={!input.trim()}>Add highlights</button>
          <button type="button" disabled={!canFit} onClick={() => union && navigate(union)}>Fit highlights</button>
          <button type="button" disabled={!highlights.length} onClick={() => { onChange([]); setMessage("Event highlights cleared."); setError(undefined); }}>Clear highlights</button></div>
        {error && <p className="event-error" role="alert">{error}</p>}
        {message && <p className="event-message" role="status">{message}</p>}
      </form>
      <div className="event-content">
        <p className="event-disclaimer">These are user-supplied positions, not annotation evidence or predicted splice/protein changes.
          Protein marks show residues touched by coding bases; introns and UTRs are not translated.
          Expand protein tracks to see their highlights.</p>
        {!!highlights.length && <ul className="event-list" aria-label="Active genomic event highlights">
          {highlights.map((interval, index) => <li key={highlightKey(interval)} style={{ borderColor: highlightColor(interval) }}>
            <button type="button" className="event-coordinate" onClick={() => navigate(interval)} title="Navigate without changing the selected gene">
              <span style={{ color: highlightColor(interval) }}>H{index + 1}</span> {highlightKey(interval)}</button>
            {interval.chrom !== gene.chrom && <small>Other chromosome</small>}
            <button type="button" aria-label={`Remove highlight ${highlightKey(interval)}`} onClick={() => onChange(highlights.filter((item) => highlightKey(item) !== highlightKey(interval)))}>×</button>
          </li>)}
        </ul>}
        {!!highlights.length && [selected, comparison].filter((tx, index, values): tx is Transcript => Boolean(tx) && values.findIndex((item) => item?.id === tx?.id) === index)
          .map((transcript) => <div className="event-projection" key={transcript.id}>
            <h3>{transcript.name} · event projection</h3>
            <table><thead><tr><th>Event</th><th>Spliced transcript bases</th><th>Protein residues touched</th></tr></thead>
              <tbody>{highlights.map((interval, index) => {
                const projection = projectGenomicEvent(interval, gene.chrom, transcript);
                return <tr key={highlightKey(interval)} data-projection-state={projection.state} data-protein-ranges={ranges(projection.protein)}>
                  <th scope="row" style={{ color: highlightColor(interval) }}>H{index + 1}</th>
                  <td>{ranges(projection.rna) || (projection.state === "intronic" ? "Intronic" : projection.state === "outside" ? "No overlap" : projection.state === "loading" ? "Loading…" : "Unavailable")}</td>
                  <td>{ranges(projection.protein) ? `${ranges(projection.protein)} aa${projection.partialCodons ? " · partial codon overlap" : ""}` : projection.proteinReason}</td>
                </tr>;
              })}</tbody></table>
          </div>)}
      </div>
    </div>
  </details>;
}
