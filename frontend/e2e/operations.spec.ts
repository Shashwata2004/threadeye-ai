import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test.setTimeout(90000);

const DATASET = process.env.E2E_DATASET ?? "sample_roll";
const PASSWORD = process.env.E2E_PASSWORD ?? "threadeye-demo-2026";
const meta = JSON.parse(readFileSync(path.resolve(__dirname, "../../data", DATASET, "roll_meta.json"), "utf8")) as {
  frames: number; fabric_width_in: number;
};
async function login(request: APIRequestContext, username: string) {
  const response = await request.post("/api/v1/auth/login", {data: {username, password: PASSWORD}});
  expect(response.status()).toBe(200);
}
async function finalized(request: APIRequestContext) {
  await login(request, "store");
  const suppliers = await (await request.get("/api/v1/suppliers")).json();
  const buyers = await (await request.get("/api/v1/buyers")).json();
  const profiles = await (await request.get("/api/v1/rule-profiles")).json() as {id: string; name: string}[];
  const lotResponse = await request.post("/api/v1/lots", {data: {challan_no: `E2E-OPS-${Date.now()}`,
    supplier_id: suppliers[0].id, buyer_id: buyers[0].id, fabric_type: "E2E synthetic fabric",
    received_at: "2026-11-03", declared_rolls: 1, rule_profile_id: profiles.find((p) => p.name === "Simulator parity")!.id}});
  expect(lotResponse.status()).toBe(201);
  const lot = await lotResponse.json();
  const rolls = await (await request.post(`/api/v1/lots/${lot.id}/rolls`, {data: {rolls: [{mill_roll_no: "OPS-1",
    declared_length_yd: 100, declared_width_in: meta.fabric_width_in}]}})).json();
  await login(request, "inspector");
  const machines = await (await request.get("/api/v1/machines")).json();
  const created = await request.post("/api/v1/inspections", {data: {roll_code: rolls[0].roll_code,
    machine_id: machines[0].id, source: {dataset_id: DATASET}, preset: "perfect"}});
  expect(created.status()).toBe(201);
  const inspection = await created.json();
  const url = `/api/v1/inspections/${inspection.id}`;
  expect((await request.post(`${url}/start`)).status()).toBe(200);
  expect((await request.post(`${url}/advance`, {data: {until_frame: meta.frames - 1, after_seq: 0}})).status()).toBe(200);
  expect((await request.post(`${url}/complete`)).status()).toBe(200);
  expect((await request.post(`${url}/defects/confirm-pending`, {data: {}})).status()).toBe(200);
  expect((await request.post(`${url}/finalize`)).status()).toBe(200);
  return inspection.id as string;
}

for (const locale of ["en", "bn"] as const) test(`operations persist (${locale}): verification, admin and cutting`, async ({page, context, baseURL}) => {
  const text = (en: string, bn: string) => locale === "en" ? en : bn;
  await context.addCookies([{name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
  await page.addInitScript((theme) => localStorage.setItem("te-theme", theme), locale === "bn" ? "dark" : "light");
  await login(page.request, "supervisor");
  await page.goto("/verification");
  await expect(page.getByTestId("verification-workbench")).toBeVisible();
  await expect(page.getByText("M4", {exact: false})).toHaveCount(0);
  await page.getByTestId("evaluation-datasets").selectOption(DATASET);
  await page.getByLabel(text("Simulation preset", "সিমুলেশনের ধরন")).selectOption("perfect");
  await page.getByTestId("evaluation-run").click();
  await expect(page.getByTestId("evaluation-history-row").first()).toContainText(text("GREEN", "সবুজ"), {timeout: 30000});
  await page.reload();
  await expect(page.getByTestId("evaluation-history-row").first()).toContainText(DATASET);
  await page.screenshot({path: `test-results/verification-${locale}.png`, fullPage: true});

  await login(page.request, "admin");
  await page.goto("/admin");
  const username = `ops_${locale}_${Date.now()}`;
  await page.getByLabel(text("Username", "ইউজারনেম"), {exact: true}).fill(username);
  await page.getByLabel(text("Display name", "নাম"), {exact: true}).fill("E2E Operator");
  await page.getByLabel(text("Initial password (10+ characters)", "প্রথম পাসওয়ার্ড (১০+ অক্ষর)")).fill("e2e-password-only");
  await page.getByRole("button", {name: text("Create account", "অ্যাকাউন্ট তৈরি"), exact: true}).click();
  await expect(page.getByRole("table")).toContainText(username);
  await page.reload();
  await expect(page.getByRole("table")).toContainText(username);
  await page.getByRole("button", {name: text("Buyer rules", "বায়ারের নিয়ম"), exact: true}).click();
  const choices = await page.getByLabel(text("Rule profile", "রুল প্রোফাইল"), {exact: true}).locator("option").all();
  await page.getByLabel(text("Rule profile", "রুল প্রোফাইল"), {exact: true}).selectOption(await choices[1].getAttribute("value") ?? "");
  await page.getByRole("button", {name: text("What-if preview", "সম্ভাব্য ফল দেখুন"), exact: true}).click();
  await expect(page.getByTestId("profile-preview")).toContainText("PASS");
  await page.getByRole("button", {name: text("Machines", "মেশিন"), exact: true}).click();
  const machineCode = `E2E_${locale}_${Date.now()}`;
  await page.getByLabel(text("Code", "কোড"), {exact: true}).fill(machineCode);
  await page.getByLabel(text("Name", "নাম"), {exact: true}).fill("E2E machine");
  await page.getByRole("button", {name: text("Save machine", "মেশিন সংরক্ষণ"), exact: true}).click();
  await expect(page.getByLabel(text("Edit machine", "মেশিন সম্পাদনা")).locator("option").filter({hasText: machineCode})).toHaveCount(1);

  const id = await finalized(page.request);
  await login(page.request, "supervisor");
  await page.goto(`/inspections/${id}/cutting`);
  await page.getByRole("button", {name: text("Approve cutting plan", "কাটিং অনুমোদন"), exact: true}).click();
  await expect(page.getByText(text("Approved", "অনুমোদিত"), {exact: true})).toBeVisible();
  await login(page.request, "cutting");
  await page.reload();
  await page.getByRole("button", {name: text("Acknowledge instructions", "নির্দেশনা গ্রহণ নিশ্চিত"), exact: true}).click();
  await expect(page.getByText(text("Acknowledged", "গ্রহণ নিশ্চিত"), {exact: true})).toBeVisible();
  const pdf = await page.request.get(`/api/v1/inspections/${id}/cutting.pdf?lang=${locale}`);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await page.screenshot({path: `test-results/cutting-${locale}.png`, fullPage: true});
  await login(page.request, "management");
  await page.goto("/");
  await expect(page.getByTestId("kpi-tiles")).toBeVisible();
  await expect(page.getByTestId("verification-status")).toBeVisible();
});

test("benchmark runs persist and compare the same held-out source", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  await login(page.request, "supervisor");
  await page.goto("/benchmark");
  await page.getByTestId("evaluation-datasets").selectOption(DATASET);
  await page.getByRole("combobox", {name: "Simulation preset", exact: true}).selectOption("perfect");
  await page.getByTestId("evaluation-run").click();
  await expect(page.getByTestId("evaluation-history-row").first()).toContainText("GREEN");
  const initialCount = await page.getByTestId("evaluation-history-row").count();
  await page.getByTestId("evaluation-run").click();
  await expect(page.getByTestId("evaluation-history-row")).toHaveCount(initialCount + 1);
  await expect(page.getByTestId("evaluation-history-row").first()).toContainText("GREEN");
  await page.getByRole("checkbox", {name: "Compare run", exact: true}).nth(0).check();
  await page.getByRole("checkbox", {name: "Compare run", exact: true}).nth(1).check();
  await expect(page.getByTestId("run-comparison")).toBeVisible();
  await expect(page.getByTestId("run-comparison")).toContainText(DATASET);
});
