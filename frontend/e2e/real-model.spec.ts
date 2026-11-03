import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

// Opt in on a laptop/edge installation with the model and line-scan video present.
// This verifies workflow conformance, not unseen-data model quality or business savings.
test("real model: live inspection, human corrections and final report", async ({page, context, baseURL}) => {
  test.skip(process.env.E2E_REAL_MODEL !== "1", "Requires local model and video assets; set E2E_REAL_MODEL=1.");
  test.setTimeout(240000);
  const password = process.env.E2E_PASSWORD ?? "threadeye-demo-2026";
  async function login(request: APIRequestContext, username: string) {
    expect((await request.post("/api/v1/auth/login", {data: {username, password}})).status()).toBe(200);
  }
  const meta = JSON.parse(readFileSync(path.resolve(__dirname, "../../data/linescan_roll/roll_meta.json"), "utf8")) as {
    fabric_width_in: number; expected_score: {verdict: string};
  };
  await context.addCookies([{name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  await login(page.request, "admin");
  expect((await page.request.put("/api/v1/admin/provider", {data: {provider_id: "local_model"}})).status()).toBe(200);
  try {
    await login(page.request, "store");
    const suppliers = await (await page.request.get("/api/v1/suppliers")).json();
    const buyers = await (await page.request.get("/api/v1/buyers")).json();
    const profiles = await (await page.request.get("/api/v1/rule-profiles")).json() as {id: string; name: string}[];
    const lot = await (await page.request.post("/api/v1/lots", {data: {challan_no: `E2E-REAL-${Date.now()}`,
      supplier_id: suppliers[0].id, buyer_id: buyers[0].id, fabric_type: "Simulated line-scan source",
      received_at: "2026-11-03", declared_rolls: 1, rule_profile_id: profiles.find((p) => p.name === "Simulator parity")!.id}})).json();
    const rolls = await (await page.request.post(`/api/v1/lots/${lot.id}/rolls`, {data: {rolls: [{mill_roll_no: "REAL-1",
      declared_length_yd: 13.123, declared_width_in: meta.fabric_width_in}]}})).json();
    await login(page.request, "inspector");
    await page.goto("/inspect");
    await page.getByTestId("roll-code").fill(rolls[0].roll_code);
    await page.getByTestId("dataset").selectOption("linescan_roll");
    await page.getByTestId("load-roll").click();
    await page.waitForURL(/\/inspect\/[0-9a-f-]{36}$/);
    const id = page.url().split("/").pop()!;
    await expect(page.getByTestId("real-model-banner")).toBeVisible();
    await page.getByRole("combobox").filter({hasText: "1×"}).selectOption("4");
    await page.getByTestId("start").click();
    await expect(page.getByTestId("defect-queue")).toBeVisible({timeout: 90000});
    await expect(page.getByTestId("finish")).toBeEnabled({timeout: 150000});
    await page.getByTestId("finish").click();
    expect((await page.request.post(`/api/v1/inspections/${id}/defects/confirm-pending`, {data: {}})).status()).toBe(200);
    // Known reviewer corrections in this regression fixture. These are not model predictions.
    for (const correction of [
      {cls: "crease_mark", center_yd: 4.291, across_cm: 133.6, length_in: 4.09},
      {cls: "broken_yarn", center_yd: 10.468, across_cm: 113.99, length_in: 4.12},
      {cls: "broken_yarn", center_yd: 12.853, across_cm: 113.93, length_in: 2.86},
    ]) expect((await page.request.post(`/api/v1/inspections/${id}/defects`, {data: {...correction,
      note: "Known human correction for workflow regression test"}})).status()).toBe(201);
    await page.reload();
    await page.getByTestId("compute-verdict").click();
    await page.waitForURL(`**/inspections/${id}`);
    await expect(page.getByTestId("system-verdict")).toHaveAttribute("data-verdict", meta.expected_score.verdict);
    const pdf = await page.request.get(`/api/v1/inspections/${id}/report.pdf?lang=bn`);
    expect(pdf.status()).toBe(200);
    expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
    await page.screenshot({path: "test-results/real-model-verdict.png", fullPage: true});
  } finally {
    await login(page.request, "admin");
    expect((await page.request.put("/api/v1/admin/provider", {data: {provider_id: "simulated"}})).status()).toBe(200);
  }
});
