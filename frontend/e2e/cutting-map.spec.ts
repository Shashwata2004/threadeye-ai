import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const id = "00000000-0000-4000-8000-000000000004";
for (const locale of ["en", "bn"] as const) {
  test(`fabric map has adjustable transparent skip zones (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    await page.addInitScript(theme => localStorage.setItem("te-theme", theme), locale === "bn" ? "dark" : "light");
    await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: false}}));
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/v1/auth/me") return route.fulfill({json: {id, username: "cutting", display_name: "Test cutting master", role: "cutting_master", permissions: ["cutting.read", "inspections.read"], locale, digit_style: "latin"}});
      if (path.endsWith("/fabric.jpg")) return process.env.E2E_FABRIC_IMAGE
        ? route.fulfill({contentType: "image/jpeg", body: await readFile(process.env.E2E_FABRIC_IMAGE)})
        : route.fulfill({contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="125"><rect width="1000" height="125" fill="#888"/></svg>'});
      if (path.endsWith("/cutting")) return route.fulfill({json: {
        inspection_id: id, source_hash: "test-plan", simulated: true, status: "draft",
        fabric: {image_url: `/api/v1/inspections/${id}/cutting/fabric.jpg`, length_yd: 13, width_cm: 150},
        defects: [{id: "d1", number: 1, cls: "broken_yarn", start_yd: 10.5, end_yd: 10.6, across_start_cm: 45, across_end_cm: 65}],
        plan: {length_yd: 13, usable_yd: 12.5, skipped_yd: 0.5, segments: [
          {start_yd: 0, end_yd: 10.4, action: "keep"}, {start_yd: 10.4, end_yd: 10.7, action: "skip"},
          {start_yd: 10.7, end_yd: 12.8, action: "keep"}, {start_yd: 12.8, end_yd: 13, action: "skip"}],
          policy: {margin_in: 3.6, min_piece_yd: 1, min_points_to_cut: 1}},
      }});
      return route.fulfill({status: 404, json: {detail: "mock endpoint unavailable"}});
    });
    await page.goto(`/inspections/${id}/cutting`);
    const map = page.getByRole("img", {name: locale === "bn" ? "স্বচ্ছ কাটিং চিহ্নসহ কাপড়ের রোল" : "Fabric roll with transparent cutting overlays"});
    await expect(map.locator("image")).toBeVisible();
    await expect(page.locator("p[role=status]")).toContainText(locale === "bn" ? "সিমুলেটেড ভিডিওর কাপড়" : "Fabric strips stitched");
    await expect(page.getByTestId("skip-overlay")).toHaveCount(2);
    await expect(page.getByTestId("skip-overlay").first()).toHaveAttribute("fill-opacity", "0.3");
    const defect = page.getByTestId("confirmed-defect-box");
    await expect(defect).toHaveCount(1);
    await expect(defect).toHaveAttribute("x", String(10.5 / 13 * 1000));
    await page.screenshot({path: `test-results/cutting-map-${locale}.png`, fullPage: true});
    await page.getByRole("slider", {name: locale === "bn" ? "লাল রঙের গাঢ়ত্ব" : "Overlay opacity"}).fill("0.1");
    await expect(page.getByTestId("skip-overlay").first()).toHaveAttribute("fill-opacity", "0.1");
    const beforeZoom = await map.boundingBox();
    await page.getByRole("slider", {name: locale === "bn" ? "বড় করে দেখুন" : "Zoom", exact: true}).fill("2");
    await expect.poll(async () => (await map.boundingBox())!.width).toBeGreaterThan(beforeZoom!.width * 1.9);
    // A failed image still leaves the instructions and the correctly placed zones usable.
    await map.locator("image").dispatchEvent("error");
    await expect(page.locator("p[role=status]")).toContainText(locale === "bn" ? "ছবি পাওয়া যাচ্ছে না" : "image unavailable");
    await expect(page.getByTestId("skip-overlay")).toHaveCount(2);
  });
}
