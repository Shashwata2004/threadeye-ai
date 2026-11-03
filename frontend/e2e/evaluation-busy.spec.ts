import { expect, test, type Page } from "@playwright/test";

async function mockEvaluation(page: Page, initial: string | null = null) {
  const state = {status: initial, runs: 0, schedules: 0};
  const run = () => ({id: "run-1", kind: "verification", status: state.status, machine_id: "machine-1",
    inspection_id: null, inputs: {}, result: state.status === "completed" ? {passed: true, rolls: []} : null,
    error: state.status === "failed" ? "test failure" : null, created_at: "2026-11-03T12:00:00Z"});
  await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: true}}));
  await page.route("**/api/**", route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path === "/api/v1/auth/me") return route.fulfill({json: {id: "user-1", username: "supervisor", role: "qc_supervisor",
      display_name: "Test supervisor", locale: "en", digit_style: "latin", permissions: ["verification.run", "verification.read"]}});
    if (path === "/api/v1/datasets") return route.fulfill({json: [{id: "test_roll"}]});
    if (path === "/api/v1/machines") return route.fulfill({json: [{id: "machine-1", code: "M-01", name: "Test machine"}]});
    if (path === "/api/v1/providers") return route.fulfill({json: [{provider_id: "simulated", availability: "available", display_name: "Simulated detector"}]});
    if (path === "/api/v1/verification/runs") {
      if (req.method() === "POST") {state.runs++; state.status = "queued"; return route.fulfill({status: 202, json: run()});}
      return route.fulfill({json: state.status ? [run()] : []});
    }
    if (path === "/api/v1/verification/schedules") {
      if (req.method() === "PUT") state.schedules++;
      return route.fulfill({json: []});
    }
    return route.fulfill({status: 404, json: {detail: "mock endpoint unavailable"}});
  });
  return state;
}

for (const locale of ["bn", "en"] as const) {
  test(`verification actions stay disabled until a queued/running check completes (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    const state = await mockEvaluation(page);
    await page.goto("/verification");
    await page.getByTestId("evaluation-datasets").selectOption("test_roll");
    const actions = page.getByTestId("verification-workbench").locator("form button");
    await expect(actions).toHaveCount(3);
    for (const button of await actions.all()) await expect(button).toBeEnabled();
    await page.getByTestId("evaluation-run").click();
    await expect(page.getByTestId("evaluation-active")).toContainText(locale === "bn" ? "অপেক্ষমাণ" : "queued");
    for (const button of await actions.all()) await expect(button).toBeDisabled();
    state.status = "running";
    await expect(page.getByTestId("evaluation-active")).toContainText(locale === "bn" ? "পরীক্ষা চলছে" : "running");
    for (const button of await actions.all()) await expect(button).toBeDisabled();
    state.status = "completed";
    await expect(page.getByTestId("evaluation-active")).toHaveCount(0);
    for (const button of await actions.all()) await expect(button).toBeEnabled();
    expect(state.runs).toBe(1);
    expect(state.schedules).toBe(0);
  });
}

test("a running check stays locked after reload and a failed check releases the actions", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  const state = await mockEvaluation(page, "running");
  await page.goto("/verification");
  await page.getByTestId("evaluation-datasets").selectOption("test_roll");
  await expect(page.getByTestId("evaluation-active")).toBeVisible();
  await page.reload();
  await page.getByTestId("evaluation-datasets").selectOption("test_roll");
  const actions = page.getByTestId("verification-workbench").locator("form button");
  for (const button of await actions.all()) await expect(button).toBeDisabled();
  state.status = "failed";
  await expect(page.getByTestId("evaluation-active")).toHaveCount(0);
  for (const button of await actions.all()) await expect(button).toBeEnabled();
  expect(state.runs).toBe(0);
});
