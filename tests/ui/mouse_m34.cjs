// Optional acceptance test against the actual full, checksum-verified M34 build.
const assert = require("node:assert/strict");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.BROWSER_ORIGIN || "http://127.0.0.1:8773";
const engine = process.env.BROWSER_ENGINE || "chromium";
const dataset = "mouse-gencode-m34";

(async () => {
  const browser = await playwright[engine].launch({ headless: true,
    ...(engine === "chromium" && process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const errors = [], external = [], checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(String(error)));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("request", request => {
      const url = new URL(request.url());
      if (/^https?:$/u.test(url.protocol) && url.origin !== origin) external.push(url.toString());
      if (url.pathname.startsWith("/api/v1/") && url.pathname !== "/api/v1/datasets") {
        assert.equal(url.searchParams.get("dataset"), dataset);
      }
    });
    await page.goto(`${origin}/?dataset=${dataset}`, { waitUntil: "networkidle" });
    await page.getByLabel("Sp1 transcript labels", { exact: true }).waitFor();
    assert.equal(await page.getByLabel("Genome annotation", { exact: true }).inputValue(), dataset);
    assert.match(await page.title(), /^Sp1 · SpliceImpactR Browser · /u);
    const manifest = await (await page.request.get(`${origin}/api/v1/manifest?dataset=${dataset}`)).json();
    assert.equal(manifest.datasetId, dataset);
    assert.equal(manifest.ensemblRelease, 111);
    assert.equal(manifest.species, "mouse");
    assert.equal(manifest.assembly, "GRCm39");
    assert.equal(manifest.capabilities.ppiPredictions, false);
    assert.equal(manifest.capabilities.ppiContext, false);
    checks.push("actual M34 opens with mouse IDs, GRCm39 and Ensembl 111, without human PPI capability");

    async function search(symbol, count) {
      const input = page.locator("#global-search-input");
      await input.fill(symbol);
      await page.getByRole("listbox").waitFor();
      await input.press("Enter");
      await page.getByLabel(`${symbol} transcript labels`, { exact: true }).waitFor();
      await page.locator(".gene-count").getByText(`${count} isoforms`, { exact: true }).waitFor();
      await page.waitForLoadState("networkidle");
    }
    for (const [symbol, count] of [["Sp1", 6], ["Tpm1", 21], ["Fgfr3", 17]]) {
      await search(symbol, count);
      const geneId = new URL(page.url()).searchParams.get("gene");
      assert.match(geneId, /^ENSMUSG/u);
      const gene = await (await page.request.get(`${origin}/api/v1/genes/${geneId}?dataset=${dataset}`)).json();
      assert.equal(gene.transcripts.length, count);
      assert.ok(gene.transcripts.every(transcript => transcript.id.startsWith("ENSMUST")));
      const menu = page.locator(".view-menu");
      if (await menu.getAttribute("open") === null) await menu.locator("summary").click();
      const all = menu.getByRole("radio", { name: "All translated transcripts", exact: true });
      if (await all.isChecked()) await menu.getByRole("button", { name: "Apply default to current gene", exact: true }).click();
      else await all.check();
      await menu.locator("summary").click();
      await page.waitForLoadState("networkidle");
      assert.equal(new URL(page.url()).searchParams.get("allProteins"), "1");
      const proteins = gene.transcripts.filter(transcript => transcript.proteinLength > 0);
      assert.ok(proteins.length >= 2);
      const aId = new URL(page.url()).searchParams.get("tx");
      const b = proteins.filter(transcript => transcript.id !== aId)
        .sort((left, right) => left.proteinLength - right.proteinLength)[0];
      await page.getByLabel("Set comparison transcript from current-gene navigator").selectOption(b.id);
      const comparison = page.locator(".feature-comparison");
      await page.waitForFunction(() => document.querySelector(".feature-comparison")?.getAttribute("data-state") === "ready");
      assert.ok((await comparison.locator(".feature-difference-row").count()) > 0);
      await page.getByLabel("Human protein interaction context", { exact: true }).waitFor();
      assert.match(await page.getByLabel("Human protein interaction context", { exact: true }).innerText(), /not applicable|human only|human-only|not available for mouse/iu);
      checks.push(`${symbol}: all ${count} source isoforms retained; All protein tracks and real feature-call comparison work`);
    }
    if (process.env.MOUSE_SCREENSHOT) await page.screenshot({ path: process.env.MOUSE_SCREENSHOT, type: "png", fullPage: true });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, engine, checks, externalRuntimeRequests: external.length,
      scope: "actual full M34 annotation and release-111 feature build; not PPI predictions" }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
