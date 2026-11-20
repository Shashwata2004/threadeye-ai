import { expect, test, type Page } from "@playwright/test";

const id = "00000000-0000-4000-8000-000000000004";

async function fixtures(page: Page, locale: string, empty = false) {
  const inspection = { id, roll_id: id, status: "completed", finalized_at: "2026-11-20T10:00:00Z",
    system_verdict: "PASS", final_verdict: null, points_total: 2, points_per_100: 10, yards_inspected: 13,
    unreviewed: 0, provider: { display_name: "Fixture AI", is_simulated: false },
    roll: { roll_code: "TEST-ROLL", challan_no: "FIXTURE", supplier: "Fixture mill", buyer: "Fixture buyer",
      lot_id: id, rule_profile: "Fixture rule", threshold_per_100: 40, declared_length_yd: 13 } };
  const defect = { inspection_id: id, kind: "defect", current_cls: "slub", predicted_cls: "slub", origin: "detector",
    status: "confirmed", length_in: 1, start_yd: 1, end_yd: 1.1, center_yd: 1.05, points: 1,
    across_start_cm: 1, across_end_cm: 2, crop_url: null, points_reason: "Fixture only", id, defect_no: "D-01" };
  const dashboard = { date: "2026-11-20", scope: "all", rolls: empty ? 0 : 6,
    verdicts: empty ? {} : { PASS: 3, BORDERLINE: 1, FAIL: 2 }, avg_per_100: 25, coverage_pct: 100,
    reviewed_detections: 0, simulated_rolls: 0, false_alarm_share: null, defect_mix: {},
    by_machine: {}, by_supplier: {}, verification: {}, active: [] };
  const cards = empty ? [] : [1, 3].map((rolls, i) => ({ id: `mill-${i}`, name: `Fixture ${i}`, rolls_inspected: rolls,
    acceptance: 1, avg_points_per_100: i ? 65 : 25, claims: 0, shortage: 0, mix: [],
    trend: [{ month: "2026-10", avg_points_per_100: i ? 65 : 25, rolls }, { month: "2026-11", avg_points_per_100: null, rolls: 0 }],
    deliveries: [{ lot_id: id, challan: `FIXTURE-${i}`, received: "2026-11-20", fabric: "Test", passed: rolls,
      review: 0, failed: 0, avg_points_per_100: i ? 65 : 25, shortage_yd: 0, status: "accepted", claims: 0, claim_eligible: false }] }));
  const evaluation = { model: "Fixture model", framework: "test", epochs: 1, train_minutes: 1, tiles: 100, defects: 10,
    classes: ["slub"], matching: "Fixture only", thresholds_from: "fixture", found_any_class: 0.8, found_right_class: 0.7,
    precision: 0.9, false_alarms_per_100_tiles: 1, nondefects_called_defect: null,
    per_source: empty ? [] : [
      { source: "aitex", tiles: 100, defects: 10, found_any_class: 0.8, found_right_class: 0.7, false_alarms_per_100_tiles: 1 },
      { source: "moratuwa", tiles: 20, defects: 0, found_any_class: null, found_right_class: null, false_alarms_per_100_tiles: 0 }],
    per_class: empty ? [] : [{ cls: "slub", nondefect: false, truth: 10, recall: 0.7, precision: 0.9, threshold: 0.5 }] };
  await page.route("**/health", route => route.fulfill({ json: { status: "ok", db: "ok", simulated_mode: false } }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") return route.fulfill({ json: { id, username: "fixture", display_name: "Fixture user", role: "management", locale,
      permissions: ["dashboard.read", "suppliers.scorecard", "inspections.read", "benchmark.read"], digit_style: "latin" } });
    if (path.endsWith("/system/status")) return route.fulfill({ json: { db: "ok", worker: { alive: false } } });
    if (path.endsWith("/providers")) return route.fulfill({ json: [] });
    if (path.endsWith("/dashboard")) return route.fulfill({ json: dashboard });
    if (path.endsWith("/suppliers/scorecard")) return route.fulfill({ json: cards });
    if (path.endsWith("/model/evaluation")) return route.fulfill({ json: evaluation });
    if (path.endsWith(`/inspections/${id}`)) return route.fulfill({ json: inspection });
    if (path.endsWith("/defects")) return route.fulfill({ json: empty ? [] : [defect,
      { ...defect, id: "second", defect_no: "D-02", center_yd: 13 },
      { ...defect, id: "rejected", defect_no: "D-03", status: "rejected", center_yd: 5 },
      { ...defect, id: "pending", defect_no: "D-04", status: "pending", center_yd: 6 },
      { ...defect, id: "nuisance", defect_no: "D-05", kind: "nondefect", current_cls: "hand", center_yd: 7 }] });
    return route.fulfill({ status: 404, json: { detail: "fixture endpoint unavailable" } });
  });
}

for (const locale of ["en", "bn"] as const) {
  test(`charts render actual values, gaps and filters (${locale})`, async ({ page, context, baseURL }) => {
    const errors: string[] = [];
    page.on("pageerror", err => errors.push(err.message));
    await context.addCookies([{ name: "te_session", value: "chart-fixture", url: baseURL! }, { name: "NEXT_LOCALE", value: locale, url: baseURL! }]);
    await page.addInitScript(theme => localStorage.setItem("te-theme", theme), locale === "bn" ? "dark" : "light");
    await fixtures(page, locale);
    await page.goto("/");
    const donut = page.getByTestId("verdict-donut");
    await expect(donut.locator(".recharts-sector")).toHaveCount(3);
    await expect(donut.locator("strong").first()).toHaveText("6");
    await donut.locator("summary").click();
    await expect(donut.getByRole("row")).toHaveCount(4);

    await page.goto("/suppliers");
    const trend = page.getByTestId("mill-trend");
    await expect(trend.locator("canvas")).toHaveAttribute("data-chart-ready", "true");
    await trend.locator("summary").click();
    await expect(trend.getByRole("row").nth(1)).toContainText("55");
    await expect(trend.getByRole("row").nth(2)).toContainText("—");
    await page.locator("select").first().selectOption("mill-0");
    await expect(trend.getByRole("row").nth(1)).toContainText("25");

    await page.goto(`/inspections/${id}`);
    const heatmap = page.getByTestId("defect-heatmap");
    await expect(heatmap.locator("[data-chart-ready]")).toHaveAttribute("data-chart-ready", "true");
    await heatmap.locator("summary").click();
    await expect(heatmap.getByRole("row")).toHaveCount(3); // only the two confirmed defects
    await expect(heatmap.getByRole("row").nth(2)).toContainText("12–13.00");
    await expect(heatmap.locator("svg")).toBeVisible();

    await page.goto("/benchmark");
    const bars = page.getByTestId("benchmark-bars");
    await expect(bars.locator("[data-chart-ready]")).toHaveAttribute("data-chart-ready", "true");
    await bars.locator("summary").click();
    await expect(bars.getByRole("row").nth(1)).toContainText("80.0%");
    await expect(bars.getByRole("row").nth(2)).toContainText("—");
    await page.getByRole("combobox", { name: locale === "bn" ? "তুলনার ধরন" : "Compare by" }).selectOption("class");
    await expect(bars.getByRole("row").nth(1)).toContainText("90.0%");
    await expect(bars.getByRole("row").nth(1)).toContainText("70.0%");
    await page.setViewportSize({ width: 390, height: 844 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("button", { name: locale === "bn" ? "লাইট মোড" : "Dark mode" }).click();
    await expect(bars.locator("[data-chart-ready]")).toHaveAttribute("data-chart-ready", "true");
    await page.screenshot({ path: `test-results/charts-${locale}.png`, fullPage: true });
    for (const [path, testId] of [["/", "verdict-donut"], ["/suppliers", "mill-trend"], [`/inspections/${id}`, "defect-heatmap"]]) {
      await page.goto(path);
      const chart = page.getByTestId(testId);
      if (testId === "verdict-donut") await expect(chart.locator(".recharts-sector")).toHaveCount(3);
      else await expect(chart.locator("[data-chart-ready]")).toHaveAttribute("data-chart-ready", "true");
      const box = await chart.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(390);
      await page.screenshot({ path: `test-results/${testId}-${locale}.png`, fullPage: true });
    }
    expect(errors).toEqual([]);
  });

  test(`empty charts do not invent measurements (${locale})`, async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: "te_session", value: "chart-fixture", url: baseURL! }, { name: "NEXT_LOCALE", value: locale, url: baseURL! }]);
    await fixtures(page, locale, true);
    for (const [path, testId] of [["/", "verdict-donut"], ["/suppliers", "mill-trend"], [`/inspections/${id}`, "defect-heatmap"], ["/benchmark", "benchmark-bars"]]) {
      await page.goto(path);
      await expect(page.getByTestId(testId).getByRole("status")).toHaveText(locale === "bn" ? "এখনো চার্ট দেখানোর তথ্য নেই।" : "No data to plot yet.");
      await expect(page.getByTestId(testId).locator("[data-chart-ready]")).toHaveCount(0);
    }
  });
}
