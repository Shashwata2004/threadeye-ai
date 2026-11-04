import { expect, test, type Page } from "@playwright/test";

// These capabilities follow security/rbac.py. API calls are mocked: no shared records change.
const roles = {
  inspector: ["dashboard.own_shift"],
  qc_supervisor: ["dashboard.read", "suppliers.scorecard", "profiles.read", "profiles.write", "cutting.read", "benchmark.read", "verification.run"],
  store_incharge: [],
  cutting_master: ["cutting.read"],
  merchandiser: ["suppliers.scorecard"],
  management: ["dashboard.read", "suppliers.scorecard", "cutting.read", "benchmark.read", "audit.read"],
  admin: ["dashboard.read", "suppliers.scorecard", "cutting.read", "benchmark.read", "audit.read", "users.manage", "verification.run"],
};

async function mockRole(page: Page, role: keyof typeof roles) {
  const requested: string[] = [];
  const permissions = ["lots.read", "inspections.read", "verification.read", "master_data.read", ...roles[role]];
  await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: true}}));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") return route.fulfill({json: {
      id: "permission-test", username: role, role, display_name: role, locale: "en", digit_style: "latin", permissions,
    }});
    requested.push(path);
    return route.fulfill({json: []});
  });
  return {permissions, requested};
}

for (const role of Object.keys(roles) as (keyof typeof roles)[]) {
  test(`${role}: denied pages explain access and readable verification stays available`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
    const {permissions, requested} = await mockRole(page, role);
    const hydrationErrors: string[] = [];
    page.on("pageerror", error => hydrationErrors.push(error.message));
    page.on("console", message => {
      if (/hydration|cannot be a descendant/i.test(message.text())) hydrationErrors.push(message.text());
    });
    for (const [path, allowed] of [
      ["/suppliers", permissions.includes("suppliers.scorecard")],
      ["/audit", permissions.includes("audit.read")],
      ["/benchmark", permissions.includes("benchmark.read")],
      ["/admin", permissions.includes("users.manage") || permissions.includes("profiles.write")],
      ["/inspections/restricted-test/cutting", permissions.includes("cutting.read")],
    ] as const) {
      if (allowed) continue;
      requested.length = 0;
      await page.goto(path);
      const notice = page.getByTestId("permission-notice");
      await expect(notice).toContainText("does not have permission");
      await expect(notice.getByRole("link")).toHaveAttribute("href", permissions.some(p => p.startsWith("dashboard.")) ? "/" : "/lots");
      await expect(page.locator("main canvas, main form")).toHaveCount(0);
      expect(requested, `denied page ${path} must not query its data`).toEqual([]);
    }
    await page.goto("/verification");
    await expect(page.getByTestId("verification-workbench")).toBeVisible();
    if (permissions.includes("verification.run")) {
      await expect(page.getByTestId("evaluation-run")).toBeVisible();
      await expect(page.getByTestId("permission-notice")).toHaveCount(0);
    } else {
      await expect(page.getByTestId("permission-notice")).toContainText("can view results but cannot run");
      await expect(page.getByTestId("evaluation-run")).toHaveCount(0);
    }
    expect(hydrationErrors).toEqual([]);
  });
}

test("QC opens buyer rules by default; restricted admin tabs explain permission", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  const {requested} = await mockRole(page, "qc_supervisor");
  await page.goto("/admin");
  await expect(page.getByText("Versioned buyer rules and preview")).toBeVisible();
  await page.getByRole("button", {name: "Users", exact: true}).click();
  await expect(page.getByTestId("permission-notice")).toContainText("cannot view this administration section");
  expect(requested).not.toContain("/api/v1/users");
  await page.getByRole("button", {name: "Buyer rules", exact: true}).click();
  await expect(page.getByTestId("permission-notice")).toHaveCount(0);
});

test("Bangla permission notice offers a usable destination", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "bn", url: baseURL!}]);
  await mockRole(page, "store_incharge");
  await page.goto("/suppliers");
  const notice = page.getByTestId("permission-notice");
  await expect(notice).toContainText("এই পেজ দেখার অনুমতি নেই");
  await expect(notice.getByRole("link")).toHaveAttribute("href", "/lots");
});
