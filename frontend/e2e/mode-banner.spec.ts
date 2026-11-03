import { expect, test } from "@playwright/test";
import en from "../messages/en.json";
import bn from "../messages/bn.json";

// UI disclosure only: no authentication, database or production service is used.
for (const [locale, messages] of [["en", en], ["bn", bn]] as const) {
  for (const theme of ["light", "dark"] as const) {
    for (const simulated of [true, false]) {
      test(`mode banner: ${locale}, ${theme}, simulated=${simulated}`, async ({ page, context, baseURL }) => {
        await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: baseURL! }]);
        await page.addInitScript((value) => localStorage.setItem("te-theme", value), theme);
        await page.route("**/health", (route) => route.fulfill({ json: {
          status: "ok", db: "ok", profile: "edge", version: "test", simulated_mode: simulated,
        } }));
        await page.goto("/login");
        const banner = page.getByTestId(simulated ? "simulated-banner" : "real-model-banner");
        await expect(banner).toHaveText(simulated ? messages.mode.simulatedBanner : messages.mode.realModelBanner);
        await expect(banner).toBeVisible();
        await expect(page.getByTestId(simulated ? "real-model-banner" : "simulated-banner")).toHaveCount(0);
        await expect(page.locator("[data-theme]").first()).toHaveAttribute("data-theme", theme);
      });
    }
  }
}
