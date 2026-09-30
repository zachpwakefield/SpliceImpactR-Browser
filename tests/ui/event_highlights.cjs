// Optional acceptance against a complete, validated human v45 or mouse M34 build.
// The oracle uses the API's coding base offsets, independently of frontend code.
const assert = require("node:assert/strict");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.BROWSER_ORIGIN || "http://127.0.0.1:8000";
const engine = process.env.BROWSER_ENGINE || "chromium";
const dataset = process.env.EVENT_DATASET || "human-gencode-v45";

function aaRanges(tx, interval) {
  if (tx.translationMapping?.status !== "exact" || !tx.proteinLength) return "";
  const counts = new Set();
  for (const piece of tx.cdsSegments) {
    if (piece.codingStart0 === null || piece.codingEnd0 === null) return "";
    for (let genomic = Math.max(piece.start0, interval.start0); genomic < Math.min(piece.end0, interval.end0); genomic++) {
      const offset = piece.codingStart0 + (tx.strand === "+" ? genomic - piece.start0 : piece.end0 - 1 - genomic);
      counts.add(Math.floor(offset / 3) + 1);
    }
  }
  const result = [];
  for (const aa of [...counts].sort((a, b) => a - b)) {
    const previous = result.at(-1);
    if (previous && aa === previous.end + 1) previous.end = aa;
    else result.push({ start: aa, end: aa });
  }
  return result.map(range => range.start === range.end ? `${range.start}` : `${range.start}–${range.end}`).join(", ");
}

(async () => {
  const browser = await playwright[engine].launch({ headless: true,
    ...(engine === "chromium" && process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const errors = [], external = [], checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: Number(process.env.EVENT_DPR || 1) });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(String(error)));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("request", request => {
      const url = new URL(request.url());
      if (/^https?:$/u.test(url.protocol) && url.origin !== origin) external.push(url.toString());
    });
    const api = async path => {
      const response = await page.request.get(`${origin}/api/v1/${path}${path.includes("?") ? "&" : "?"}dataset=${dataset}`);
      assert.equal(response.status(), 200, path);
      return response.json();
    };
    const manifest = await api("manifest");
    assert.equal(manifest.capabilities.genomicEventHighlights, true);
    assert.ok(manifest.chromosomeLengths.chrX > 100000000);
    await page.goto(`${origin}/?dataset=${dataset}`, { waitUntil: "networkidle" });
    const panel = page.locator(".event-highlights");
    const symbols = dataset.startsWith("mouse") ? ["Sp1", "Tpm1", "Fgfr3", "Brca1"] : ["SP1", "TPM1", "FGFR3", "TP53"];
    async function openPanel() { if (await panel.getAttribute("open") === null) await panel.locator("summary").click(); }
    async function add(text) {
      await openPanel();
      await panel.getByLabel("Genomic intervals", { exact: true }).fill(text);
      await panel.getByRole("button", { name: "Add highlights", exact: true }).click();
    }
    async function search(symbol) {
      const input = page.locator("#global-search-input");
      await input.fill(symbol);
      await page.getByRole("listbox").waitFor();
      await input.press("Enter");
      await page.getByLabel(`${symbol} transcript labels`, { exact: true }).waitFor();
      await page.waitForLoadState("networkidle");
    }
    let lastEvents, lastTx, savedSession;
    for (const symbol of symbols) {
      if (await panel.locator(".event-list li").count()) await panel.getByRole("button", { name: "Clear highlights", exact: true }).click();
      await search(symbol);
      await openPanel();
      const before = new URL(page.url()).searchParams;
      const gene = await api(`genes/${before.get("gene")}`);
      const tx = await api(`transcripts/${before.get("tx")}`);
      assert.equal(tx.translationMapping.status, "exact", `${symbol} primary map`);
      const cds = tx.cdsSegments.filter(piece => piece.codingStart0 !== null).slice(0, 2);
      assert.equal(cds.length, 2);
      const events = cds.map(piece => ({ chrom: gene.chr, start0: piece.start0, end0: Math.min(piece.end0, piece.start0 + 60) }));
      const ordered = [...tx.exons].sort((a, b) => a.start0 - b.start0);
      const gapIndex = ordered.findIndex((exon, index) => index && exon.start0 - ordered[index - 1].end0 > 20);
      assert.ok(gapIndex > 0);
      const intronStart = ordered[gapIndex - 1].end0 + 3;
      events.push({ chrom: gene.chr, start0: intronStart, end0: intronStart + 10 });
      const utr = tx.utrSegments.find(piece => piece.end0 > piece.start0);
      if (utr) events.push({ chrom: gene.chr, start0: utr.start0, end0: Math.min(utr.end0, utr.start0 + 8) });
      await add(`${gene.chr}:${events.map(interval => `${interval.start0 + 1}-${interval.end0}`).join(",")}`);
      assert.equal(await panel.locator(".event-error").count(), 0);
      assert.equal(await panel.locator(".event-list li").count(), events.length);
      const after = new URL(page.url()).searchParams;
      for (const key of ["gene", "tx", "locus"]) assert.equal(after.get(key), before.get(key), `${key} unchanged by add`);
      const rows = panel.locator(".event-projection").first().locator("tbody tr");
      for (let i = 0; i < events.length; i++) assert.equal(await rows.nth(i).getAttribute("data-protein-ranges"), aaRanges(tx, events[i]));
      assert.equal(await rows.nth(2).getAttribute("data-projection-state"), "intronic");
      if (utr) assert.equal(await rows.nth(3).getAttribute("data-protein-ranges"), "");
      assert.ok(Number(await page.locator("canvas").getAttribute("data-protein-highlight-count")) > 0);
      assert.equal(Number(await page.locator("canvas").getAttribute("data-genomic-highlight-count")), events.length);
      const alternative = gene.transcripts.find(other => other.id !== tx.id && other.proteinLength > 0);
      if (alternative) {
        await page.getByLabel("Set comparison transcript from current-gene navigator").selectOption(alternative.id);
        await page.waitForLoadState("networkidle");
        const b = await api(`transcripts/${alternative.id}`);
        const bRows = panel.locator(".event-projection").nth(1).locator("tbody tr");
        await bRows.first().waitFor();
        for (let i = 0; i < events.length; i++) assert.equal(await bRows.nth(i).getAttribute("data-protein-ranges"), aaRanges(b, events[i]));
      }
      await panel.getByRole("button", { name: "Fit highlights", exact: true }).click();
      const fitted = new URL(page.url()).searchParams.get("locus");
      assert.match(fitted, new RegExp(`^${gene.chr}:`));
      const listBeforePan = new URL(page.url()).searchParams.get("hi");
      await panel.locator("summary").click();
      await page.locator("canvas").focus();
      await page.keyboard.press("ArrowRight");
      await page.keyboard.press("+");
      assert.equal(new URL(page.url()).searchParams.get("hi"), listBeforePan);
      await openPanel();
      checks.push(`${symbol} ${tx.strand} strand: genomic list, exact protein map, intron/UTR states, comparison, fit and pan/zoom`);
      lastEvents = events; lastTx = tx;
    }
    if (process.env.EVENT_SCREENSHOT) {
      await page.getByRole("tab", { name: "Transcript", exact: true }).click();
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: process.env.EVENT_SCREENSHOT, fullPage: true });
    }
    const eventCount = lastEvents.length;
    await add("chrX:1-3,bad");
    assert.match(await panel.getByRole("alert").innerText(), /Use chrX/);
    assert.equal(await panel.locator(".event-list li").count(), eventCount);
    await add(`chrX:${manifest.chromosomeLengths.chrX + 1}-${manifest.chromosomeLengths.chrX + 3}`);
    assert.match(await panel.getByRole("alert").innerText(), /exceeds/);
    assert.equal(await panel.locator(".event-list li").count(), eventCount);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export session", exact: true }).click();
    const download = await downloadPromise, stream = await download.createReadStream(), chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    savedSession = Buffer.concat(chunks);
    assert.ok(new URLSearchParams(JSON.parse(savedSession.toString("utf8")).urlState).has("hi"));
    await panel.getByRole("button", { name: "Clear highlights", exact: true }).click();
    assert.equal(await panel.locator(".event-list li").count(), 0);
    await page.goBack();
    assert.equal(await panel.locator(".event-list li").count(), eventCount);
    await page.goForward();
    assert.equal(await panel.locator(".event-list li").count(), 0);
    await page.locator('input[type="file"]').setInputFiles({ name: "event-session.json", mimeType: "application/json", buffer: savedSession });
    await page.waitForFunction(count => document.querySelectorAll(".event-list li").length === count, eventCount);
    const hi = new URL(page.url()).searchParams.get("hi");
    await page.reload({ waitUntil: "networkidle" });
    await openPanel();
    assert.equal(new URL(page.url()).searchParams.get("hi"), hi);
    assert.equal(await panel.locator(".event-list li").count(), eventCount);
    checks.push("invalid input is atomic; highlights survive Back/Forward, session export/import and reload");

    // A manual locus jump keeps gene context; it must not misattribute the
    // same numeric coordinates on another chromosome to that gene's protein.
    await add("chrM:1-3");
    const oldGene = new URL(page.url()).searchParams.get("gene");
    await panel.getByRole("button", { name: /H\d+ chrM:1-3/u }).click();
    assert.equal(new URL(page.url()).searchParams.get("gene"), oldGene);
    assert.match(new URL(page.url()).searchParams.get("locus"), /^chrM:/u);
    const otherChromRow = panel.locator(".event-projection").first().locator("tbody tr").last();
    assert.equal(await otherChromRow.getAttribute("data-projection-state"), "outside");
    assert.equal(await otherChromRow.getAttribute("data-protein-ranges"), "");
    checks.push("other-chromosome navigation preserves context without a false RNA/protein projection");

    const menu = page.getByLabel("Genome annotation", { exact: true });
    const target = dataset === "human-gencode-v45" ? "mouse-gencode-m34" : "human-gencode-v45";
    if (await menu.locator(`option[value="${target}"]`).count()) {
      await menu.selectOption(target);
      await page.waitForFunction(id => new URLSearchParams(location.search).get("dataset") === id, target);
      await page.locator(".event-highlights").waitFor();
      await page.waitForLoadState("networkidle");
      assert.equal(await page.locator(".event-list li").count(), 0);
      await page.getByLabel("Genome annotation", { exact: true }).selectOption(dataset);
      await page.waitForFunction(id => new URLSearchParams(location.search).get("dataset") === id, dataset);
      await page.waitForLoadState("networkidle");
      await openPanel();
      assert.equal(await panel.locator(".event-list li").count(), eventCount + 1);
      checks.push("human/mouse switch isolates highlights by dataset/build and restores the original workspace on return");
    }
    await panel.getByRole("button", { name: "Fit highlights", exact: true }).click();
    await page.setViewportSize({ width: 780, height: 900 });
    const hideDetails = page.getByRole("button", { name: "Hide details", exact: true });
    if (await hideDetails.count()) await hideDetails.click();
    await page.waitForTimeout(200);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    if (process.env.EVENT_NARROW_SCREENSHOT) await page.screenshot({ path: process.env.EVENT_NARROW_SCREENSHOT, fullPage: true });
    assert.equal(lastTx.strand, "-", "TP53/Brca1 tests reverse-strand mapping");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, dataset, engine, dpr: Number(process.env.EVENT_DPR || 1), checks,
      browserErrors: errors.length, externalRuntimeRequests: external.length }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
