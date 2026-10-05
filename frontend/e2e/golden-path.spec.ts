import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type APIRequestContext } from "@playwright/test";

// M2 acceptance: the core flow in a real browser against the running app.
//   load roll → start → video plays, boxes drawn → confirm every defect → finish → verdict → defect photos → PDF
// With the perfect preset and the simulator-parity profile the verdict must equal the roll's
// roll_meta.json expected_score. The page must not make a single request outside the app (offline).

const DATASET = process.env.E2E_DATASET ?? "sample_roll";
const PASSWORD = process.env.E2E_PASSWORD ?? "threadeye-demo-2026"; // demo accounts (.env.example)
const META = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../data", DATASET, "roll_meta.json"), "utf-8"),
) as { fabric_width_in: number; expected_score: { total_points: number; points_per_100_sq_yd: number; verdict: string } };

async function login(request: APIRequestContext, username: string) {
  const r = await request.post("/api/v1/auth/login", { data: { username, password: PASSWORD } });
  expect(r.status(), `login ${username}`).toBe(200);
}

async function registerRoll(request: APIRequestContext): Promise<string> {
  await login(request, "store");
  const suppliers = await (await request.get("/api/v1/suppliers")).json();
  const buyers = await (await request.get("/api/v1/buyers")).json();
  const profiles: { id: string; name: string }[] = await (await request.get("/api/v1/rule-profiles")).json();
  const parity = profiles.find((p) => p.name === "Simulator parity");
  expect(parity, "seeded simulator-parity profile").toBeTruthy();
  const lot = await (
    await request.post("/api/v1/lots", {
      data: {
        challan_no: `E2E-${Date.now()}`,
        supplier_id: suppliers[0].id,
        buyer_id: buyers[0].id,
        fabric_type: "E2E twill",
        received_at: new Date().toISOString().slice(0, 10),
        declared_rolls: 1,
        rule_profile_id: parity!.id,
      },
    })
  ).json();
  const rolls = await (
    await request.post(`/api/v1/lots/${lot.id}/rolls`, {
      data: { rolls: [{ mill_roll_no: "E2E-1", declared_length_yd: 100, declared_width_in: META.fabric_width_in }] },
    })
  ).json();
  await request.post("/api/v1/auth/logout");
  return rolls[0].roll_code as string;
}

for (const lang of ["bn", "en"] as const) test(`core flow (${lang}): live inspection to verdict and report, offline`, async ({ page, request, baseURL }) => {
  const appHost = new URL(baseURL!).host;
  const outside: string[] = [];
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.host === appHost || url.protocol === "data:" || url.protocol === "blob:") return route.continue();
    outside.push(url.href);
    return route.abort();
  });

  const rollCode = await registerRoll(request);

  // Inspector logs in (UI).
  await page.goto("/login");
  await page.locator("input:not([type=password])").first().fill("inspector");
  await page.locator("input[type=password]").fill(PASSWORD);
  await page.locator("button[type=submit]").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await expect(page.getByTestId("simulated-banner")).toBeVisible();
  // The inspector's UI language (saved per user), switched with the header toggle.
  await page.getByRole("button", { name: lang === "bn" ? "বাংলা" : "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", lang);

  // Load the roll on the machine.
  await page.goto("/inspect");
  await page.getByTestId("roll-code").fill(rollCode);
  await page.getByTestId("dataset").selectOption(DATASET);
  await page.getByTestId("preset").selectOption("perfect");
  await page.getByTestId("load-roll").click();
  await page.waitForURL(/\/inspect\/[0-9a-f-]{36}$/);
  const inspectionId = page.url().split("/").pop()!;

  // Live run at 4× demo speed.
  await page.getByRole("combobox").filter({ hasText: "1×" }).selectOption("4");
  await page.getByTestId("start").click();
  await expect(page.getByTestId("points-meter")).toBeVisible();
  await expect(page.getByTestId("defect-queue")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("finish")).toBeEnabled({ timeout: 150_000 });
  expect(await page.getByTestId("roll-video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(1);

  await page.getByTestId("finish").click();
  await expect(page.getByTestId("compute-verdict")).toBeVisible();

  // The inspector confirms every defect (perfect preset: every one is real).
  const confirm = page.getByTestId("confirm");
  for (let left = await confirm.count(); left > 0; left = await confirm.count()) {
    await confirm.first().click();
    await expect(confirm).toHaveCount(left - 1);
  }
  await expect(page.getByTestId("compute-verdict")).toBeEnabled();
  await page.getByTestId("compute-verdict").click();

  // Verdict page: same score as the simulator's answer.
  await page.waitForURL(`**/inspections/${inspectionId}`);
  const es = META.expected_score;
  await expect(page.getByTestId("system-verdict")).toHaveAttribute("data-verdict", es.verdict);
  // Language-independent: the inspector's own UI language (Bangla) applies after login.
  await expect(page.getByTestId("verdict-summary")).toHaveText(new RegExp(`^${es.total_points}\\D`));
  await expect(page.getByTestId("verdict-summary")).toContainText(es.points_per_100_sq_yd.toFixed(2));
  await expect(page.getByTestId("defect-gallery")).toBeVisible();
  await expect(page.getByTestId("defects-table")).toBeVisible();

  // Report PDF, labelled SIMULATED.
  const pdf = await page.request.get(`/api/v1/inspections/${inspectionId}/report.pdf?lang=en`);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  expect(outside, "requests that left the app").toEqual([]);
});
