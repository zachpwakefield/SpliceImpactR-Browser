// Optional real-browser checks against a complete v45 build with the separately
// prepared public human PPI context. Synthetic API tests cover unavailable/mouse.
const assert = require("node:assert/strict");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.BROWSER_ORIGIN || "http://127.0.0.1:8000";
const engine = process.env.BROWSER_ENGINE || "chromium";
const dataset = "human-gencode-v45";

(async () => {
  const browser = await playwright[engine].launch({ headless: true,
    ...(engine === "chromium" && process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const errors = [], external = [], checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(String(error)));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("request", request => { const url = new URL(request.url()); if (/^https?:$/u.test(url.protocol) && url.origin !== origin) external.push(url.toString()); });
    await page.goto(`${origin}/?dataset=${dataset}`, { waitUntil: "networkidle" });
    await page.getByLabel("SP1 transcript labels", { exact: true }).waitFor();
    assert.equal(await page.locator(".brand-copy strong").innerText(), "SpliceImpactR Browser");
    assert.equal(await page.locator(".brand-mark").innerText(), "SB");
    assert.match(await page.title(), /^SP1 · SpliceImpactR Browser · /u);
    await page.getByRole("button", { name: "About & diagnostics", exact: true }).click();
    await page.getByRole("heading", { name: /^SpliceImpactR Browser /u }).waitFor();
    assert.match(await page.locator(".diagnostics-dialog pre").innerText(), /^SpliceImpactR Browser diagnostics/u);
    await page.getByRole("button", { name: "Close About and Diagnostics", exact: true }).click();
    const sessionPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export session", exact: true }).click();
    const session = await sessionPromise;
    assert.match(session.suggestedFilename(), /^spliceimpactr-browser-[0-9a-f]+\.json$/u);
    const sessionStream = await session.createReadStream(), sessionChunks = [];
    for await (const chunk of sessionStream) sessionChunks.push(chunk);
    assert.equal(JSON.parse(Buffer.concat(sessionChunks).toString("utf8")).format, "local-transcript-browser-session");
    checks.push("new product identity appears in the toolbar, browser title, About/diagnostics and session filename while the session format stays compatible");
    if (process.env.EXPANDED_SCREENSHOT) {
      await page.getByRole("tab", { name: "Transcript", exact: true }).click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(250);
      await page.screenshot({ path: process.env.EXPANDED_SCREENSHOT, type: "jpeg" });
    }
    if (process.env.SEQUENCE_SCREENSHOT) {
      await page.getByRole("tab", { name: "Sequence", exact: true }).click();
      await page.locator(".sequence-line").first().waitFor();
      await page.waitForTimeout(250);
      await page.screenshot({ path: process.env.SEQUENCE_SCREENSHOT, type: "jpeg" });
    }
    const manifest = await (await page.request.get(`${origin}/api/v1/manifest?dataset=${dataset}`)).json();
    assert.equal(manifest.capabilities.ppiContext, true);
    assert.equal(manifest.capabilities.ppiPredictions, false);
    const gene = await (await page.request.get(`${origin}/api/v1/genes/ENSG00000185591?dataset=${dataset}`)).json();
    const aId = new URL(page.url()).searchParams.get("tx");
    const a = gene.transcripts.find(transcript => transcript.id === aId);
    const b = gene.transcripts.filter(transcript => transcript.proteinLength > 0 && transcript.id !== aId)
      .sort((left, right) => left.proteinLength - right.proteinLength)[0];
    assert.ok(a && b);
    await page.getByLabel("Set comparison transcript from current-gene navigator").selectOption(b.id);
    const featurePanel = page.locator(".feature-comparison");
    await featurePanel.locator('.feature-difference-row').first().waitFor();
    assert.equal(await featurePanel.getAttribute("data-state"), "ready");
    assert.ok(await featurePanel.locator('[data-difference="selected-only"]').count() > 0);
    assert.ok(await featurePanel.locator(".feature-difference-row").count() <= 12);
    assert.match(await featurePanel.innerText(), /not aligned residues/);
    const differences = await featurePanel.locator(".feature-difference-row").count();
    await featurePanel.getByLabel("Show differences only", { exact: true }).uncheck();
    assert.ok(await featurePanel.locator(".feature-difference-row").count() >= differences);
    await featurePanel.getByRole("searchbox", { name: "Find feature name or accession", exact: true }).fill("PF00096");
    await featurePanel.locator(".feature-difference-row").first().waitFor();
    assert.match(await featurePanel.innerText(), /PF00096/);
    await featurePanel.getByRole("searchbox", { name: "Find feature name or accession", exact: true }).fill("");
    checks.push("real SP1 comparison shows individual calls, one-sided observations, shared-call toggle and accession search");

    const pfamChip = page.locator(".source-chip").filter({ has: page.getByRole("checkbox", { name: /^(Hide|Show) Pfam,/ }) });
    await pfamChip.click();
    assert.equal(await page.getByRole("checkbox", { name: /^Show Pfam,/ }).isChecked(), false);
    assert.ok(await featurePanel.locator("code").filter({ hasText: "PF00096" }).count() > 0, "Canvas filters must not hide comparison evidence");
    await pfamChip.click();
    assert.equal(await page.getByRole("checkbox", { name: /^Hide Pfam,/ }).isChecked(), true);
    checks.push("Canvas feature filters do not hide the complete comparison evidence");

    const downloadPromise = page.waitForEvent("download");
    await featurePanel.getByRole("button", { name: "Feature calls TSV", exact: true }).click();
    const download = await downloadPromise;
    assert.match(download.suggestedFilename(), /protein-feature-comparison\.tsv$/u);
    const stream = await download.createReadStream(), chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    assert.match(body, /source_availability_json/);
    assert.match(body, /provenance\thuman-gencode-v45/);
    assert.match(body, /selected-only/);
    assert.match(body, /outsideStoredProteinBounds/);
    checks.push("complete feature-call TSV downloads with annotation/protein provenance and bounds audit");

    const ppi = page.getByLabel("Human protein interaction context", { exact: true });
    await page.getByRole("button", { name: "Go to PPI context", exact: true }).click();
    await ppi.locator(".ppi-record").first().waitFor();
    assert.match(await ppi.innerText(), /97 matching resource records/);
    assert.match(await ppi.innerText(), /330 total gene records/);
    assert.match(await ppi.innerText(), /Observed/);
    assert.match(await ppi.innerText(), /Not observed/);
    assert.ok(await ppi.locator(".ppi-record").count() <= 12);
    const first = await ppi.locator(".ppi-record").first().innerText();
    await ppi.getByRole("button", { name: "Next partners", exact: true }).click();
    await page.waitForLoadState("networkidle");
    await ppi.locator(".ppi-record").first().waitFor();
    assert.notEqual(await ppi.locator(".ppi-record").first().innerText(), first);
    await ppi.getByRole("button", { name: "Previous partners", exact: true }).click();
    await ppi.locator(".ppi-record").first().waitFor();
    await ppi.getByLabel("Interaction records", { exact: true }).selectOption("all");
    await page.waitForFunction(() => document.querySelector(".ppi-record-counts")?.textContent?.includes("330 matching resource records"));
    await ppi.getByLabel("Interaction records", { exact: true }).selectOption("feature-linked");
    await ppi.locator(".ppi-record").first().waitFor();
    await ppi.getByText("Interaction provenance and limitations", { exact: true }).click();
    assert.match(await ppi.innerText(), /not asserted to be Ensembl-release-matched/);
    checks.push("real human PPI context is gene-level, endpoint-owned, paged, data-hashed and distinct from disabled predictions");

    // Inspect B's actual call, not just a metric: the comparison pair must survive.
    const bButton = featurePanel.locator('.feature-comparison-pair section').filter({ has: page.locator("h6", { hasText: `Comparison · ${b.name}` }) }).getByRole("button").first();
    await bButton.click();
    assert.equal(new URL(page.url()).searchParams.get("tx"), b.id);
    assert.equal(new URL(page.url()).searchParams.get("compareTx"), a.id);
    await page.getByRole("tab", { name: "Compare", exact: true }).click();
    await featurePanel.locator(".feature-difference-row").first().waitFor();
    assert.equal(await page.locator(".comparison-panel").getAttribute("data-selected-transcript-id"), b.id);
    assert.equal(await page.locator(".comparison-panel").getAttribute("data-comparison-transcript-id"), a.id);
    await page.getByRole("button", { name: "Swap selected and comparison", exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get("tx"), a.id);
    assert.equal(new URL(page.url()).searchParams.get("compareTx"), b.id);
    checks.push("comparison-side feature inspection and explicit swap preserve both transcripts and feature ownership");
    await page.waitForLoadState("networkidle");
    if (process.env.BROWSER_SCREENSHOT) {
      await page.getByRole("button", { name: "Go to protein features", exact: true }).click();
      await page.waitForTimeout(250); // Only screenshot settling; never a readiness assertion.
      await page.screenshot({ path: process.env.BROWSER_SCREENSHOT, type: process.env.BROWSER_SCREENSHOT.endsWith(".jpg") ? "jpeg" : "png" });
    }
    if (process.env.PPI_SCREENSHOT) {
      await page.getByRole("button", { name: "Go to PPI context", exact: true }).click();
      await ppi.locator(".ppi-record").first().waitFor();
      await page.waitForTimeout(250);
      await page.screenshot({ path: process.env.PPI_SCREENSHOT, type: process.env.PPI_SCREENSHOT.endsWith(".jpg") ? "jpeg" : "png" });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, engine, checks, externalRuntimeRequests: external.length,
      scope: "actual full v45 feature calls and separate public human PPI context; not isoform PPI predictions" }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
