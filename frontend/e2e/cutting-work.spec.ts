import { expect, test } from "@playwright/test";

for (const locale of ["bn", "en"]) {
  test(`cutting master lands on approved instructions and can find acknowledged work (${locale})`, async ({page, context, baseURL}) => {
    const missingMessages: string[] = [];
    page.on("console", message => {
      if (/MISSING_MESSAGE|Could not resolve/.test(message.text())) missingMessages.push(message.text());
    });
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: true}}));
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/auth/me")) return route.fulfill({json: {id: "cutting-user", username: "cutting", role: "cutting_master",
        display_name: "Cutting", locale, digit_style: "latin", permissions: ["cutting.read", "cutting.acknowledge", "lots.read", "inspections.read", "verification.read"]}});
      if (path === "/api/v1/cutting") return route.fulfill({json: [
        {inspection_id: "approved-1", roll_code: "TE-000001", challan: "CH-1", status: "approved",
          approved_at: "2026-11-04T01:00:00Z", acknowledged_at: null, usable_yd: 12, skipped_yd: 1},
        {inspection_id: "approved-2", roll_code: "TE-000002", challan: "CH-2", status: "approved",
          approved_at: "2026-11-04T01:00:00Z", acknowledged_at: null, usable_yd: 10, skipped_yd: 3},
        {inspection_id: "received-1", roll_code: "TE-000003", challan: "CH-3", status: "acknowledged",
          approved_at: "2026-11-03T01:00:00Z", acknowledged_at: "2026-11-04T01:00:00Z", usable_yd: 9, skipped_yd: 4},
      ]});
      return route.fulfill({status: 404, json: {detail: "mock endpoint unavailable"}});
    });
    await page.goto("/");
    await expect(page).toHaveURL(/\/cutting$/);
    await expect(page.locator('nav[aria-label="main"] a[href="/cutting"]')).toHaveText(locale === "bn" ? "কাটিং কাজ" : "Cutting work");
    const table = page.getByTestId("cutting-work-list");
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await expect(table).toContainText("TE-000001");
    await expect(table).toContainText("TE-000002");
    await expect(table.getByRole("link").first()).toHaveAttribute("href", "/inspections/approved-1/cutting");
    await page.locator("main select").selectOption("acknowledged");
    await expect(table.locator("tbody tr")).toHaveCount(1);
    await expect(table).toContainText("TE-000003");
    await page.locator("main select").selectOption("all");
    await expect(table.locator("tbody tr")).toHaveCount(3);
    expect(missingMessages).toEqual([]);
  });
}
