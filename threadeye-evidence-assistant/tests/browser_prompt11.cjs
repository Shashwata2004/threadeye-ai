"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const {spawn} = require("child_process");

const project = path.resolve(__dirname, "..");
const playwrightModule = process.env.PLAYWRIGHT_MODULE;
const chrome = process.env.CHROME_EXECUTABLE;
if (!playwrightModule || !chrome) throw new Error("PLAYWRIGHT_MODULE and CHROME_EXECUTABLE are required");
const {chromium} = require(playwrightModule);
const origin = "http://127.0.0.1:8770";
const screenshots = path.join(project, "docs", "evidence", "screenshots");
fs.mkdirSync(screenshots, {recursive: true});
const accessCode = `qa-${crypto.randomBytes(24).toString("base64url")}`;
const child = spawn(path.join(project, ".venv", "bin", "python"), ["-m", "threadeye_evidence.ui.launcher"], {
  cwd: project,
  env: {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONPATH: path.join(project, "src"),
    THREADEYE_EVIDENCE_UI_ACCESS_CODE: accessCode,
  },
  stdio: ["ignore", "ignore", "pipe"],
});
let serverLog = "";
child.stderr.on("data", chunk => { serverLog += chunk.toString(); });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
async function waitReady() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`judge UI exited during startup: ${serverLog.trim()}`);
    try {
      const response = await fetch(`${origin}/healthz`);
      if (response.status === 200) return;
    } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error("judge UI did not become ready");
}
async function login(page, code) {
  await page.goto(origin, {waitUntil: "domcontentloaded"});
  await page.locator("#access-code").fill(code);
  await Promise.all([
    page.waitForNavigation({waitUntil: "domcontentloaded"}),
    page.getByRole("button", {name: "Enter secure demonstration"}).click(),
  ]);
}
async function stopChild() {
  if (child.exitCode !== null) return;
  child.kill("SIGINT");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 5000)),
  ]);
  if (child.exitCode === null) child.kill("SIGTERM");
}

(async () => {
  let browser;
  const started = Date.now();
  try {
    await waitReady();
    browser = await chromium.launch({headless: true, executablePath: chrome});
    const invalid = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const invalidPage = await invalid.newPage();
    await login(invalidPage, "incorrect-code-value");
    assert((await invalidPage.locator(".form-error").textContent()).includes("Access denied"), "invalid login was not rejected");
    await invalidPage.screenshot({path: path.join(screenshots, "prompt11-invalid-login.png"), fullPage: true});
    await invalid.close();

    const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
    const loginStart = Date.now();
    await login(page, accessCode);
    await page.getByText("MCP connected", {exact: true}).waitFor({timeout: 15000});
    const loginAndOverviewMs = Date.now() - loginStart;
    const cookies = await context.cookies();
    const session = cookies.find(cookie => cookie.name === "threadeye_ui_session");
    assert(session && session.httpOnly && session.sameSite === "Strict", "secure local session cookie attributes missing");
    const browserStorage = await page.evaluate(() => ({local: Object.keys(localStorage), session: Object.keys(sessionStorage)}));
    assert(browserStorage.local.length === 0 && browserStorage.session.length === 0, "browser storage contains unexpected keys");
    await page.keyboard.press("Tab");
    assert(await page.locator(":focus").getAttribute("href") === "#main-content", "skip-link keyboard focus failed");
    assert(await page.locator('[role="status"][aria-live="polite"]').count() >= 3, "accessible live status regions missing");
    const unauth = await page.request.get(`${origin}/api/overview`, {headers: {Cookie: ""}});
    assert(unauth.status() === 401, "unauthenticated API access did not fail closed");
    await page.screenshot({path: path.join(screenshots, "prompt11-overview-desktop.png"), fullPage: true});

    await page.locator("#search-query").fill("content hash sanitized observation");
    const searchStart = Date.now();
    await page.getByRole("button", {name: "Search evidence", exact: true}).click();
    await page.getByText("3 authorized result(s) returned through MCP.", {exact: true}).waitFor({timeout: 15000});
    const searchMs = Date.now() - searchStart;
    assert(await page.locator(".evidence-card").count() === 3, "real MCP search did not return three cards");
    assert(await page.locator(".evidence-meta").first().textContent().then(text => text.includes("technical-evidence.md")), "source metadata missing");
    await page.screenshot({path: path.join(screenshots, "prompt11-search-desktop.png"), fullPage: true});

    await page.locator("#ask-question").fill("Which supplier lot is recorded for ROLL-NST-204?");
    const answerStart = Date.now();
    await page.getByRole("button", {name: "Ask evidence", exact: true}).click();
    await page.getByText("ANSWERED", {exact: true}).waitFor({timeout: 15000});
    const answerMs = Date.now() - answerStart;
    assert((await page.locator(".answer-text").textContent()).includes("LOT-FX-17"), "grounded answer omitted the supplier lot");
    await page.locator(".citation-button").first().click();
    await page.locator("#citation-dialog[open]").waitFor();
    assert((await page.locator("#citation-metadata").textContent()).includes("technical-evidence.md"), "citation source metadata missing");
    assert((await page.locator("#citation-excerpt").textContent()).includes("LOT-FX-17"), "citation excerpt does not support answer");
    assert(
      await page.locator("#citation-close").evaluate(element => element === document.activeElement),
      "citation close control did not receive focus",
    );
    await page.screenshot({path: path.join(screenshots, "prompt11-citation-desktop.png"), fullPage: true});
    await page.locator("#citation-close").press("Enter");

    await page.locator("#ask-question").fill("What is tomorrow's weather in Dhaka?");
    await page.getByRole("button", {name: "Ask evidence", exact: true}).click();
    await page.getByText("ABSTAINED", {exact: true}).waitFor({timeout: 15000});
    assert((await page.locator(".abstention-card").textContent()).includes("insufficient_relevance"), "safe abstention reason missing");
    await page.screenshot({path: path.join(screenshots, "prompt11-abstention-desktop.png"), fullPage: true});

    assert(consoleErrors.length === 0, `successful browser flows logged console errors: ${consoleErrors.join(" | ")}`);
    consoleErrors.length = 0;
    const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
    const invalidPayload = await page.evaluate(async token => {
      const response = await fetch("/api/search", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRF-Token": token}, body: JSON.stringify({query: "x", mode: "hybrid", top_k: 3, extra: true})});
      return response.status;
    }, csrf);
    assert(invalidPayload === 400, "unexpected JSON fields were not rejected");
    const csrfRejected = await page.evaluate(async () => (await fetch("/api/search", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRF-Token": "invalid"}, body: JSON.stringify({query: "x", mode: "hybrid", top_k: 3})})).status);
    assert(csrfRejected === 403, "invalid CSRF token was not rejected");
    const oversized = await page.evaluate(async token => (await fetch("/api/search", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRF-Token": token}, body: JSON.stringify({query: "x".repeat(9000), mode: "hybrid", top_k: 3})})).status, csrf);
    assert(oversized === 413, "oversized request was not rejected");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "desktop horizontal overflow detected");
    const expectedNegativeHttpConsoleEntries = consoleErrors.length;

    await page.locator("#logout-button").click();
    await page.locator("#access-code").waitFor();
    const afterLogout = await page.request.get(`${origin}/api/overview`);
    assert(afterLogout.status() === 401, "logout did not invalidate the session");
    await context.close();

    const mobile = await browser.newContext({viewport: {width: 390, height: 844}});
    const mobilePage = await mobile.newPage();
    const mobileErrors = [];
    mobilePage.on("console", message => { if (message.type() === "error") mobileErrors.push(message.text()); });
    await login(mobilePage, accessCode);
    await mobilePage.getByText("MCP connected", {exact: true}).waitFor({timeout: 15000});
    assert(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "mobile horizontal overflow detected");
    assert(mobileErrors.length === 0, `mobile console errors: ${mobileErrors.join(" | ")}`);
    await mobilePage.screenshot({path: path.join(screenshots, "prompt11-overview-mobile.png"), fullPage: true});
    await mobile.close();

    console.log(JSON.stringify({
      status: "passed",
      browser: "Google Chrome via Playwright",
      playwright_version: require(path.join(playwrightModule, "package.json")).version,
      viewports: ["1440x1000", "390x844"],
      login_and_overview_ms: loginAndOverviewMs,
      search_interaction_ms: searchMs,
      answer_interaction_ms: answerMs,
      total_runtime_ms: Date.now() - started,
      desktop_overflow: false,
      mobile_overflow: false,
      console_errors_during_success_paths: 0,
      expected_negative_http_console_entries: expectedNegativeHttpConsoleEntries,
      local_storage_keys: 0,
      session_storage_keys: 0,
      session_cookie: {http_only: true, same_site: "Strict"},
      screenshots: [
        "prompt11-invalid-login.png", "prompt11-overview-desktop.png", "prompt11-search-desktop.png",
        "prompt11-citation-desktop.png", "prompt11-abstention-desktop.png", "prompt11-overview-mobile.png",
      ],
    }, null, 2));
  } finally {
    if (browser) await browser.close();
    await stopChild();
  }
})().catch(error => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
