import type { CodingSegment, Locus, Transcript, TranscriptExon } from "../types";
import { MAX_LOCUS_SPAN_BP } from "./coordinates";

export const MAX_EVENT_HIGHLIGHTS = 100;
export const MAX_HIGHLIGHT_INPUT_CHARACTERS = 12_000;
const COLORS = ["#be662d", "#a5537d", "#507baa", "#947325", "#7665ad", "#438378"];
const CHROMOSOME = /^[A-Za-z0-9_.-]{1,60}$/u;
const NUMBER = /^(?:\d+|\d{1,3}(?:,\d{3})+)$/u;

export function highlightKey(interval: Locus): string {
  return `${interval.chrom}:${interval.start0 + 1}-${interval.end0}`;
}

export function highlightColor(interval: Locus): string {
  let hash = 0;
  for (const character of highlightKey(interval)) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return COLORS[hash % COLORS.length];
}

export function validateHighlights(value: unknown): Locus[] {
  if (!Array.isArray(value) || value.length > MAX_EVENT_HIGHLIGHTS) throw new Error(`Use at most ${MAX_EVENT_HIGHLIGHTS} highlights.`);
  const seen = new Set<string>();
  return value.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("Invalid genomic highlight.");
    const interval = raw as Locus;
    if (typeof interval.chrom !== "string" || !CHROMOSOME.test(interval.chrom) || !Number.isSafeInteger(interval.start0)
      || !Number.isSafeInteger(interval.end0) || interval.start0 < 0 || interval.end0 <= interval.start0
      || interval.end0 - interval.start0 > MAX_LOCUS_SPAN_BP) {
      throw new Error("Highlights need a chromosome and a valid 1-based inclusive interval, at most 25 Mb long.");
    }
    return { chrom: interval.chrom, start0: interval.start0, end0: interval.end0 };
  }).filter((interval) => {
    const key = highlightKey(interval);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** A list uses ungrouped numbers; one interval per line can use thousands commas. */
export function parseHighlightInput(text: string, defaultChrom?: string): Locus[] {
  if (text.length > MAX_HIGHLIGHT_INPUT_CHARACTERS) throw new Error("Highlight input is too long.");
  if (!text.trim()) throw new Error("Enter at least one genomic interval.");
  let chromosome = defaultChrom;
  const intervals: Locus[] = [];
  for (const line of text.split(/[;\n]+/u).map((line) => line.trim()).filter(Boolean)) {
    const numericPart = line.includes(":") ? line.slice(line.indexOf(":") + 1) : line;
    const rangeCount = (numericPart.match(/-|\.\./gu) ?? []).length;
    const tokens = rangeCount > 1 ? line.split(",") : [line];
    for (const token of tokens) {
      const match = /^\s*(?:([A-Za-z0-9_.-]+)\s*:\s*)?([\d,]+)\s*(?:-|\.\.)\s*([\d,]+)\s*$/u.exec(token);
      if (!match || !NUMBER.test(match[2]) || !NUMBER.test(match[3])) {
        throw new Error("Use chrX:1-3,5-9,22-50. For thousands separators, put each complete interval on its own line.");
      }
      if (match[1]) {
        const name = match[1].replace(/^chr/iu, "");
        chromosome = `chr${/^(?:x|y|m|mt)$/iu.test(name) ? (name.toUpperCase() === "MT" ? "M" : name.toUpperCase()) : name}`;
      }
      if (!chromosome) throw new Error("Include a chromosome, for example chrX:1-3.");
      const start1 = Number(match[2].replaceAll(",", ""));
      const end1 = Number(match[3].replaceAll(",", ""));
      intervals.push({ chrom: chromosome, start0: start1 - 1, end0: end1 });
    }
  }
  if (!intervals.length) throw new Error("Enter at least one genomic interval.");
  return validateHighlights(intervals);
}

export function checkHighlightBounds(intervals: readonly Locus[], lengths?: Record<string, number>): void {
  if (!intervals.length) return;
  if (!lengths || !Object.keys(lengths).length) throw new Error("Chromosome bounds are unavailable. Restart the updated local server.");
  for (const interval of intervals) {
    const length = lengths[interval.chrom];
    if (!Number.isSafeInteger(length) || length <= 0) throw new Error(`${interval.chrom} is not in the selected genome annotation.`);
    if (interval.end0 > length) throw new Error(`${highlightKey(interval)} exceeds ${interval.chrom}'s length in this assembly.`);
  }
}

export interface EventProjection {
  state: "outside" | "loading" | "error" | "intronic" | "exonic";
  rna: { start1: number; end1: number; exonRank: number }[];
  protein: { start1: number; end1: number }[];
  proteinReason: string;
  partialCodons: boolean;
}

function orderedExons(transcript: Transcript): TranscriptExon[] | null {
  if (![transcript.start0, transcript.end0, transcript.transcriptLength].every(Number.isSafeInteger)
    || transcript.start0 < 0 || transcript.end0 <= transcript.start0 || transcript.transcriptLength <= 0) return null;
  const exons = [...transcript.exons].sort((a, b) => a.rank - b.rank);
  let offset = 0;
  for (const [index, exon] of exons.entries()) {
    if (exon.rank !== index + 1 || !Number.isSafeInteger(exon.start0) || !Number.isSafeInteger(exon.end0)
      || exon.end0 <= exon.start0 || exon.start0 < 0
      || exon.start0 < transcript.start0 || exon.end0 > transcript.end0
      || (exon.transcriptStart0 !== undefined && exon.transcriptStart0 !== offset)
      || (exon.transcriptEnd0 !== undefined && exon.transcriptEnd0 !== offset + exon.end0 - exon.start0)) return null;
    if (index && (transcript.strand === "+" ? exons[index - 1].end0 > exon.start0 : exons[index - 1].start0 < exon.end0)) return null;
    offset += exon.end0 - exon.start0;
  }
  return exons.length && offset === transcript.transcriptLength ? exons : null;
}

function exactCodingPieces(transcript: Transcript, exons: TranscriptExon[]): CodingSegment[] | null {
  if (transcript.translationMapping?.status !== "exact" || !Number.isSafeInteger(transcript.proteinLength)
    || transcript.proteinLength <= 0 || !Number.isSafeInteger(3 * transcript.proteinLength)) return null;
  const pieces = [...(transcript.codingSegments ?? [])].sort((a, b) => a.codingStart0 - b.codingStart0);
  const exonOffsets = new Map<number, number>();
  let rnaOffset = 0;
  for (const exon of exons) { exonOffsets.set(exon.rank, rnaOffset); rnaOffset += exon.end0 - exon.start0; }
  let next = 0;
  let origin: number | undefined;
  for (const piece of pieces) {
    const exon = exons.find((exon) => exon.rank === piece.exonRank);
    if (![piece.start0, piece.end0, piece.exonRank, piece.codingStart0, piece.codingEnd0].every(Number.isSafeInteger)
      || piece.start0 < 0 || piece.end0 <= piece.start0 || piece.codingStart0 !== next
      || piece.codingEnd0 - piece.codingStart0 !== piece.end0 - piece.start0
      || !exon || exon.start0 > piece.start0 || exon.end0 < piece.end0) return null;
    const rnaStart = exonOffsets.get(piece.exonRank)! + (transcript.strand === "+" ? piece.start0 - exon.start0 : exon.end0 - piece.end0);
    origin ??= rnaStart;
    // Contiguous coding offsets must also be contiguous on the spliced RNA.
    // A reordered or gapped response must not fabricate a protein projection.
    if (rnaStart - piece.codingStart0 !== origin) return null;
    next = piece.codingEnd0;
  }
  // FASTA header CDS bounds may include the terminal stop triplet, whereas
  // the exact GTF coding pieces (and protein length) deliberately exclude it.
  const headerEnd = transcript.translationMapping.cdsEnd0;
  if ((transcript.translationMapping.cdsStart0 !== undefined && transcript.translationMapping.cdsStart0 !== origin)
    || (headerEnd !== undefined && headerEnd !== (origin ?? 0) + next && headerEnd !== (origin ?? 0) + next + 3)) return null;
  return pieces.length && next === 3 * transcript.proteinLength ? pieces : null;
}

/** Touched residues, not mutation effects. Split codons retain transcript order on either strand. */
export function projectGenomicEvent(interval: Locus, geneChrom: string, transcript: Transcript): EventProjection {
  const result: EventProjection = { state: "outside", rna: [], protein: [], proteinReason: "Outside this transcript", partialCodons: false };
  if (interval.chrom !== geneChrom || interval.end0 <= transcript.start0 || interval.start0 >= transcript.end0) return result;
  if (transcript.detailState !== "ready") return { ...result, state: transcript.detailState === "error" ? "error" : "loading", proteinReason: "Transcript geometry not loaded" };
  const exons = orderedExons(transcript);
  if (!exons) return { ...result, state: "error", proteinReason: "Transcript coordinate map is incomplete or inconsistent" };
  let offset = 0;
  for (const exon of exons) {
    const start = Math.max(interval.start0, exon.start0), end = Math.min(interval.end0, exon.end0);
    if (end > start) result.rna.push({
      start1: offset + (transcript.strand === "+" ? start - exon.start0 : exon.end0 - end) + 1,
      end1: offset + (transcript.strand === "+" ? end - exon.start0 : exon.end0 - start), exonRank: exon.rank,
    });
    offset += exon.end0 - exon.start0;
  }
  result.state = result.rna.length ? "exonic" : "intronic";
  if (!result.rna.length) return { ...result, proteinReason: "Intronic — no exonic bases" };
  if (!transcript.proteinLength) return { ...result, proteinReason: "No translated product" };
  const pieces = exactCodingPieces(transcript, exons);
  if (!pieces) return { ...result, proteinReason: `Not projected: ${transcript.translationMapping?.status ?? "unverified"} coding map` };
  const ntRanges: { start0: number; end0: number }[] = [];
  for (const piece of pieces) {
    const start = Math.max(interval.start0, piece.start0), end = Math.min(interval.end0, piece.end0);
    if (end <= start) continue;
    const ntStart = piece.codingStart0 + (transcript.strand === "+" ? start - piece.start0 : piece.end0 - end);
    const ntEnd = piece.codingStart0 + (transcript.strand === "+" ? end - piece.start0 : piece.end0 - start);
    const previous = ntRanges.at(-1);
    if (previous && ntStart <= previous.end0) previous.end0 = Math.max(previous.end0, ntEnd);
    else ntRanges.push({ start0: ntStart, end0: ntEnd });
  }
  for (const ntRange of ntRanges) {
    result.partialCodons ||= ntRange.start0 % 3 !== 0 || ntRange.end0 % 3 !== 0;
    const range = { start1: Math.floor(ntRange.start0 / 3) + 1, end1: Math.floor((ntRange.end0 - 1) / 3) + 1 };
    const previous = result.protein.at(-1);
    if (previous && range.start1 <= previous.end1 + 1) previous.end1 = Math.max(previous.end1, range.end1);
    else result.protein.push({ ...range });
  }
  result.proteinReason = result.protein.length ? "Residues touched by genomic bases; not a predicted protein change" : "Exonic, outside translated CDS (e.g. UTR)";
  return result;
}
