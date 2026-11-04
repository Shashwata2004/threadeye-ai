import { expect, test } from "@playwright/test";

for (const locale of ["bn", "en"]) {
  test(`recent inspections show QC decision and cutting handoff independently (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: true}}));
    await page.route("**/api/**", route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/auth/me")) return route.fulfill({json: {id: "test-user", username: "cutting", role: "cutting_master",
        display_name: "Cutting", permissions: ["inspections.read", "lots.read", "cutting.read"]}});
      if (url.pathname === "/api/v1/inspections") return route.fulfill({json: url.searchParams.get("open_only") ? [] : [
        {id: "accepted", roll_code: "TE-01", status: "completed", system_verdict: "BORDERLINE", final_verdict: "ACCEPT", cutting_status: "approved"},
        {id: "claimed", roll_code: "TE-02", status: "completed", system_verdict: "FAIL", final_verdict: "ACCEPT_WITH_CLAIM", cutting_status: "acknowledged"},
        {id: "returned", roll_code: "TE-03", status: "completed", system_verdict: "PASS", final_verdict: "REJECT", cutting_status: "not_issued"},
        {id: "pending", roll_code: "TE-04", status: "completed", system_verdict: "PASS", final_verdict: null, cutting_status: "draft"},
        {id: "aborted", roll_code: "TE-05", status: "aborted", system_verdict: null, final_verdict: null, cutting_status: "not_ready"},
      ]});
      return route.fulfill({json: []});
    });
    await page.goto("/inspect");
    const accepted = page.getByTestId("inspection-progress-accepted");
    await expect(accepted).toContainText(locale === "bn" ? "QC সিদ্ধান্ত: গ্রহণ" : "QC decision: Accept");
    await expect(accepted).toContainText(locale === "bn" ? "কাটিং নির্দেশনা: অনুমোদিত" : "Cutting instructions: Approved");
    await expect(accepted).toContainText(locale === "bn" ? "গ্রহণ: অপেক্ষমাণ" : "receipt: Awaiting receipt");
    const claimed = page.getByTestId("inspection-progress-claimed");
    await expect(claimed).toContainText(locale === "bn" ? "দাবি সহ গ্রহণ" : "Accept with a claim");
    await expect(claimed).toContainText(locale === "bn" ? "নিশ্চিত করেছেন" : "Acknowledged");
    const returned = page.getByTestId("inspection-progress-returned");
    await expect(returned).toContainText(locale === "bn" ? "ফেরত" : "Reject (return to mill)");
    await expect(returned).toContainText(locale === "bn" ? "দেওয়া হয়নি" : "Not issued");
    await expect(page.getByTestId("inspection-progress-pending")).toContainText(locale === "bn" ? "QC সিদ্ধান্ত: অপেক্ষমাণ" : "QC decision: Pending");
    await expect(page.getByTestId("inspection-progress-pending")).toContainText(locale === "bn" ? "খসড়া" : "Draft");
    await expect(page.getByTestId("inspection-progress-aborted")).toHaveCount(0);
  });
}
