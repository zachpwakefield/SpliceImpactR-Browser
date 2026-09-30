export const APPLICATION_NAME = "SpliceImpactR Browser";
export const APPLICATION_MARK = "SB";
export const APPLICATION_FILE_PREFIX = "spliceimpactr-browser";
export const APPLICATION_VERSION = "1.3.0";

export function applicationDocumentTitle(geneSymbol?: string, release?: string): string {
  return [geneSymbol, APPLICATION_NAME, release].filter(Boolean).join(" · ");
}
