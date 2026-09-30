// Optional real-browser regression against a complete local human v45 build.
// Playwright is a test-only external dependency, never a runtime requirement.
const assert = require("node:assert/strict");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.BROWSER_ORIGIN || "http://127.0.0.1:8000";
const engine = process.env.BROWSER_ENGINE || "chromium";
const dataset = "human-gencode-v45";

(async () => {
  const browser = await playwright[engine].launch({ headless: true,
    ...(engine === "chromium" && process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const errors = [], external = [], featureRequests = [], checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(String(error)));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("request", request => {
      const url = new URL(request.url());
      if (/^https?:$/u.test(url.protocol) && url.origin !== origin) external.push(url.toString());
      const match = url.pathname.match(/\/transcripts\/([^/]+)\/features$/u);
      if (match) featureRequests.push(decodeURIComponent(match[1]));
    });
    await page.goto(`${origin}/?dataset=${dataset}`, { waitUntil: "networkidle" });
    await page.getByLabel("SP1 transcript labels", { exact: true }).waitFor();
    const expandedRows = () => page.locator('.disclosure-button[aria-expanded="true"]');
    async function preference(label) {
      const menu = page.locator(".view-menu");
      if (await menu.getAttribute("open") === null) await menu.locator("summary").click();
      const radio = menu.getByRole("radio", { name: label, exact: true });
      if (await radio.isChecked()) await menu.getByRole("button", { name: "Apply default to current gene", exact: true }).click();
      else await radio.check();
      await menu.locator("summary").click();
    }
    async function search(symbol, count) {
      const input = page.locator("#global-search-input");
      await input.fill(symbol);
      await page.getByRole("listbox").waitFor();
      await input.press("Enter");
      await page.getByLabel(`${symbol} transcript labels`, { exact: true }).waitFor();
      await page.locator(".gene-count").getByText(`${count} isoforms`, { exact: true }).waitFor();
    }
    async function waitExpandedCount(count) {
      await page.waitForFunction(expected => document.querySelectorAll('.disclosure-button[aria-expanded="true"]').length === expected, count);
    }
    await waitExpandedCount(1);
    await preference("All translated transcripts");
    await waitExpandedCount(4);
    assert.equal(new URL(page.url()).searchParams.get("allProteins"), "1");
    assert.equal(new URL(page.url()).searchParams.get("expanded"), "");
    await page.getByRole("button", { name: "Collapse SP1-202 protein annotations", exact: true }).click();
    await page.getByRole("button", { name: "Expand SP1-202 protein annotations", exact: true }).waitFor();
    await page.waitForFunction(() => Object.entries(localStorage).some(([key, value]) =>
      key.startsWith("transcript-browser:workspace:v1:") && JSON.parse(value).proteinExpansionDefault === "all"));
    await page.reload({ waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Expand SP1-202 protein annotations", exact: true }).waitFor();
    await page.getByRole("button", { name: "Collapse SP1-201 protein annotations", exact: true }).waitFor();
    await page.getByRole("button", { name: "Expand SP1-202 protein annotations", exact: true }).click();
    await page.getByRole("button", { name: "Collapse SP1-202 protein annotations", exact: true }).waitFor();
    checks.push("All opens every translated SP1 row; individual collapse/reopen survives an explicit URL reload");
    await page.getByLabel("Set comparison transcript from current-gene navigator").selectOption("ENST00000327443");
    await preference("Top translated transcript");
    assert.equal(new URL(page.url()).searchParams.get("tx"), "ENST00000327443");
    assert.equal(new URL(page.url()).searchParams.get("compareTx"), null);
    checks.push("choosing Top clears a comparison that would otherwise equal the new selection");

    await preference("None");
    await waitExpandedCount(0);
    await search("TPM1", 39);
    await waitExpandedCount(0);
    await preference("Top translated transcript");
    await waitExpandedCount(1);
    await page.getByRole("button", { name: "Collapse TPM1-207 protein annotations", exact: true }).waitFor();
    await preference("All translated transcripts");
    await page.getByRole("button", { name: "Collapse TPM1-229 protein annotations", exact: true }).waitFor();
    assert.ok(await expandedRows().count() > 1);
    checks.push("None applies to a new gene; Top opens only TPM1-207; All also opens TPM1-229");

    await search("FGFR3", 10);
    assert.equal(new URL(page.url()).searchParams.get("allProteins"), "1");
    assert.ok(await expandedRows().count() > 1);
    featureRequests.length = 0;
    await search("ANK2", 129);
    const gene = await (await page.request.get(`${origin}/api/v1/genes/ENSG00000145362?dataset=${dataset}`)).json();
    const proteins = gene.transcripts.filter(transcript => transcript.proteinLength > 0);
    assert.ok(proteins.length > 25);
    await page.waitForLoadState("networkidle");
    const proteinIds = new Set(proteins.map(transcript => transcript.id));
    const initialRequests = new Set(featureRequests.filter(id => proteinIds.has(id)));
    assert.ok(initialRequests.size < proteins.length, "All must not eagerly fetch every isoform");
    assert.ok(await page.locator(".transcript-label-row").count() <= 16, "All must retain vertical virtualization");
    const finalProtein = proteins[proteins.length - 1];
    await page.getByLabel("Matching transcripts in current visual order").selectOption(finalProtein.id);
    await page.getByRole("button", { name: `Collapse ${finalProtein.name} protein annotations`, exact: true }).waitFor();
    assert.ok(await page.locator(".transcript-label-row").count() <= 16);
    checks.push("All includes ANK2 translated rows beyond 25 while DOM and initial feature requests remain window-bounded");

    async function explicitRestoreDuringLoad(symbol, geneId, transcriptId, kind) {
      let received, release;
      const pending = new Promise(resolve => { received = resolve; });
      const gate = new Promise(resolve => { release = resolve; });
      const routePattern = `${origin}/api/v1/genes/${geneId}?*`;
      await page.route(routePattern, async route => { received(); await gate; await route.continue(); });
      const input = page.locator("#global-search-input");
      await input.fill(symbol);
      await page.getByRole("listbox").waitFor();
      await input.press("Enter");
      let timer;
      await Promise.race([pending, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("Expected delayed gene request was not issued")), 30000);
      })]).finally(() => clearTimeout(timer));
      const url = new URL(page.url());
      url.searchParams.set("gene", geneId);
      url.searchParams.set("tx", transcriptId);
      url.searchParams.set("mode", "labeled");
      url.searchParams.set("expanded", "");
      url.searchParams.set("allProteins", "0");
      url.searchParams.set("collapsedProteins", "");
      if (kind === "history") {
        await page.evaluate(search => {
          history.replaceState({}, "", location.pathname + search);
          dispatchEvent(new PopStateEvent("popstate"));
        }, url.search);
      } else {
        const session = { format: "local-transcript-browser-session", version: 2,
          buildHash: url.searchParams.get("build"), datasetId: dataset,
          urlState: url.search, annotations: {} };
        await page.locator('input[type="file"]').setInputFiles({ name: "explicit-view.json",
          mimeType: "application/json", buffer: Buffer.from(JSON.stringify(session)) });
        await page.waitForFunction(() => new URL(location.href).searchParams.get("allProteins") === "0");
      }
      release();
      await page.getByLabel(`${symbol} transcript labels`, { exact: true }).waitFor();
      await waitExpandedCount(0);
      assert.equal(new URL(page.url()).searchParams.get("allProteins"), "0");
      assert.equal(new URL(page.url()).searchParams.get("mode"), "labeled");
      await page.unroute(routePattern);
    }
    await explicitRestoreDuringLoad("PGK1", "ENSG00000102144", "ENST00000373316", "history");
    await explicitRestoreDuringLoad("EGFR", "ENSG00000146648", "ENST00000275493", "session");
    checks.push("explicit history and session restoration override a pending All default during delayed gene loading");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, engine, checks, externalRuntimeRequests: external.length,
      scope: "complete local human v45 protein-track preference regression" }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
