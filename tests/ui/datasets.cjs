// Optional real-browser contract test against the synthetic API datasets.
// Requires Playwright externally; it is not a runtime browser dependency.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.BROWSER_ORIGIN || "http://127.0.0.1:8771";
const engine = process.env.BROWSER_ENGINE || "chromium";

(async () => {
  const browser = await playwright[engine].launch({ headless: true,
    ...(engine === "chromium" && process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
  const errors = [], external = [], checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    async function open(dataset, symbol) {
      const page = await context.newPage();
      page.on("pageerror", error => errors.push(String(error)));
      page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
      page.on("request", request => {
        const url = new URL(request.url());
        if (url.protocol === "http:" || url.protocol === "https:") {
          if (url.origin !== origin) external.push(url.toString());
          if (url.pathname.startsWith("/api/v1/") && url.pathname !== "/api/v1/datasets") {
            assert.equal(url.searchParams.get("dataset"), dataset, "all tab API requests are scoped");
          }
        }
      });
      await page.goto(`${origin}/?dataset=${dataset}`, { waitUntil: "networkidle" });
      await page.getByLabel(`${symbol} transcript labels`, { exact: true }).waitFor();
      const selector = page.getByLabel("Genome annotation", { exact: true });
      assert.equal(await selector.locator("option").count(), 4);
      assert.equal(await selector.inputValue(), dataset);
      assert.equal(new URL(page.url()).searchParams.get("dataset"), dataset);
      return page;
    }
    const human = await open("human-gencode-v45", "SP1");
    const mouse = await open("mouse-gencode-m39", "Sp1");
    const matchedMouse = await open("mouse-gencode-m34", "Sp1");
    const v50 = await open("human-gencode-v50", "SP1");
    await mouse.getByLabel("ELM unavailable for this dataset", { exact: true }).waitFor();
    assert.ok(await mouse.getByLabel("ELM unavailable for this dataset", { exact: true }).isDisabled());
    assert.ok((await mouse.locator(".build-badge").textContent()).includes("GRCm39"));
    assert.ok((await matchedMouse.locator(".build-badge").textContent()).includes("M34"));
    assert.ok((await matchedMouse.locator(".build-badge").textContent()).includes("111"));
    for (const [page, residue] of [[mouse, "M"], [matchedMouse, "G"], [mouse, "M"]]) {
      const response = await page.request.get(`${origin}/api/v1/transcripts/ENSMUST00000327443/sequence?dataset=${new URL(page.url()).searchParams.get("dataset")}`);
      assert.equal((await response.json()).sequence[0], residue);
    }
    checks.push("four independent tabs retain species/release identity; M34 and M39 do not cross-load shared mouse transcript IDs");
    for (const [page, residue] of [[human, "M"], [v50, "A"], [human, "M"]]) {
      const response = await page.request.get(`${origin}/api/v1/transcripts/ENST00000327443/sequence?dataset=${new URL(page.url()).searchParams.get("dataset")}`);
      assert.equal((await response.json()).sequence[0], residue);
    }
    checks.push("same stable transcript ID cannot cross-load sequence between v45 and v50");

    const inspector = human.getByLabel("Selection inspector");
    await inspector.getByRole("tab", { name: "Gene", exact: true }).click();
    const note = inspector.getByLabel(/^Local user note/);
    await note.fill("Dataset isolation test note");
    await human.waitForFunction(() => Boolean(document.querySelector('[data-unsaved-annotation="true"]')));
    await human.getByLabel("Genome annotation", { exact: true }).selectOption("human-gencode-v50");
    await human.getByText("Complete pending note/tag edits before switching annotation. Wait for autosave or use Save now.", { exact: true }).waitFor();
    assert.equal(new URL(human.url()).searchParams.get("dataset"), "human-gencode-v45");
    await human.waitForFunction(() => !document.querySelector('[data-unsaved-annotation="true"]'));
    // Request tracking switches with the new document only.
    human.removeAllListeners("request");
    await human.getByLabel("Genome annotation", { exact: true }).selectOption("human-gencode-v50");
    await human.waitForURL(url => url.searchParams.get("dataset") === "human-gencode-v50");
    await human.getByLabel("SP1 transcript labels", { exact: true }).waitFor();
    const saved = await human.evaluate(() => Object.entries(localStorage).filter(([key]) => key.startsWith("transcript-browser:workspace:v1:")));
    assert.ok(saved.some(([key, value]) => key.includes("human-gencode-v45") && value.includes("Dataset isolation test note")));
    assert.ok(!saved.some(([key, value]) => key.includes("human-gencode-v50") && value.includes("Dataset isolation test note")));
    assert.equal(await mouse.getByLabel("Genome annotation", { exact: true }).inputValue(), "mouse-gencode-m39");
    checks.push("pending note edits block switching; saved notes stay in the original dataset/build workspace");
    await human.getByLabel("Selection inspector").getByRole("tab", { name: "Gene", exact: true }).click();
    for (const link of await human.locator('.inspector-content a[href^="/api/v1/export"]').all()) {
      assert.equal(new URL(await link.getAttribute("href"), origin).searchParams.get("dataset"), "human-gencode-v50");
    }
    const output = process.env.BROWSER_OUTPUT_DIRECTORY || fs.mkdtempSync(path.join(os.tmpdir(), "dataset-ui-"));
    fs.mkdirSync(output, { recursive: true });
    await mouse.screenshot({ path: path.join(output, `${engine}-mouse.png`), fullPage: true });
    const unknown = await context.newPage();
    await unknown.goto(`${origin}/?dataset=unknown`, { waitUntil: "networkidle" });
    await unknown.locator(".startup-workspace").getByText("No verified local annotation is loaded", { exact: true }).waitFor();
    assert.equal(await unknown.locator(".transcript-label-row").count(), 0);
    checks.push("unknown dataset fails visibly without a fallback annotation");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ passed: true, engine, checks, externalRuntimeRequests: external.length, scope: "synthetic dataset UI contract, not full biological installation" }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
