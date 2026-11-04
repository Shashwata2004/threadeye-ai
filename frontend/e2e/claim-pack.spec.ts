import { expect, test, type Page } from "@playwright/test";

async function mockClaims(page: Page, eligible: boolean, role = "merchandiser") {
  const state = {ok: false, requests: 0, decision: null as string | null};
  await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: true}}));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({json: {id: "test-user", role, display_name: "Test user",
      permissions: ["suppliers.scorecard", "claims.write", "lots.read", "verdict.decide"]}});
    if (path === "/api/v1/suppliers/scorecard") return route.fulfill({json: [{id: "mill-1", name: "Test mill", rolls_inspected: 2,
      acceptance: 1, avg_points_per_100: 38, claims: eligible ? 1 : 0, shortage: .5, trend: [], mix: [], deliveries: [
        {lot_id: "lot-1", challan: "CH-1", received: "2026-11-04", fabric: "Cotton", passed: 2, review: 0, failed: 0,
          avg_points_per_100: 38, shortage_yd: 188.4, claims: eligible ? 1 : 0,
          lot_decision: eligible ? "ACCEPT_WITH_REJECTS" : null, claim_eligible: eligible, status: eligible ? "accepted" : "review"},
      ]} ]});
    if (path.endsWith("/claim-pack.zip")) {
      state.requests++;
      return state.ok ? route.fulfill({contentType: "application/zip", body: Buffer.from("504b0506000000000000000000000000000000000000", "hex")}) :
        route.fulfill({status: 409, json: {detail: "Delivery decision required"}});
    }
    if (path === "/api/v1/lots/lot-1") return route.fulfill({json: {id: "lot-1", challan_no: "CH-1", supplier: {name: "Mill"}, buyer: {name: "Buyer"},
      fabric_type: "Cotton", received_at: "2026-11-04", rolls_registered: 2, declared_rolls: 2}});
    if (path.endsWith("/verdict") || path.endsWith("/decision")) {
      if (route.request().method() === "POST") state.decision = route.request().postDataJSON().decision;
      return route.fulfill({json: {status: "ACCEPT", required_sample: 1, inspected: 2, failed: 0, fail_pct: 0, total_rolls: 2,
        rules: {hold_if_fail_pct_over: 20, reject_if_fail_pct_over: 50}, rolls: [], claim_eligible: false,
        decision: state.decision ? {decision: state.decision, reason: "Checked sample", decided_by: "QC supervisor"} : null}});
    }
    if (path.endsWith("/sampling-suggestion")) return route.fulfill({status: 404, json: {detail: "mock unavailable"}});
    return route.fulfill({json: []});
  });
  return state;
}

for (const locale of ["bn", "en"]) {
  test(`under-review claim stays blocked; delivery decision is reachable (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    const state = await mockClaims(page, false, "qc_supervisor");
    await page.goto("/suppliers");
    await expect(page.getByTestId("claim-pack")).toBeDisabled();
    expect(state.requests).toBe(0);
    await page.getByRole("link", {name: locale === "bn" ? "চালানের সিদ্ধান্ত দিন" : "Record delivery decision"}).click();
    await expect(page).toHaveURL(/\/lots\/lot-1#lot-decision$/);
    await expect(page.locator("#lot-decision")).toContainText(locale === "bn" ? "পুরো চালানের সিদ্ধান্ত" : "whole delivery");
    await page.getByTestId("lot-decision-choice").selectOption("ACCEPT");
    await page.getByTestId("lot-decision-reason").fill("Checked sample");
    await page.locator("#lot-decision button").last().click();
    await expect(page.getByTestId("lot-decision")).toContainText("QC supervisor");
    expect(state.decision).toBe("ACCEPT");
    await expect(page.getByTestId("lot-claim-pack")).toBeDisabled();
  });

  test(`failed claim download never shows success; successful ZIP starts a download (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    const state = await mockClaims(page, true);
    await page.goto("/suppliers");
    const button = page.getByTestId("claim-pack");
    await button.click();
    await expect(page.locator("main").getByRole("alert")).toContainText("Delivery decision required");
    await expect(page.locator("main").getByRole("status")).toHaveCount(0);
    state.ok = true;
    const downloaded = page.waitForEvent("download");
    await button.click();
    expect((await downloaded).suggestedFilename()).toBe("claim-pack-lot-1.zip");
    await expect(page.locator("main").getByRole("status")).toContainText(locale === "bn" ? "ডাউনলোড শুরু হয়েছে" : "download started");
    await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
    expect(state.requests).toBe(2);
  });
}
