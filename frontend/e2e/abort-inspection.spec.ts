import { expect, test, type Page } from "@playwright/test";
import en from "../messages/en.json";
import bn from "../messages/bn.json";

test.setTimeout(45000);
const OLD_ID = "00000000-0000-4000-8000-000000000004";
const NEW_ID = "00000000-0000-4000-8000-000000000005";
const ROLL = "TE-000004";

async function mockInspections(page: Page, {readOnly = false, fail = false} = {}) {
  let aborted = false;
  const requests: {aborts: number; createdRoll: string | null} = {aborts: 0, createdRoll: null};
  const item = {id: OLD_ID, roll_id: OLD_ID, roll_code: ROLL, status: "created", system_verdict: null,
    inspector: "Test inspector", model_outdated: false, checkpoint_frame: -1};
  await page.route("**/health", (route) => route.fulfill({json: {
    status: "ok", db: "ok", profile: "edge", version: "ui-test", simulated_mode: true,
  }}));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/auth/me") return route.fulfill({json: {
      id: OLD_ID, username: "inspector", display_name: "Test inspector", role: readOnly ? "management" : "inspector",
      locale: "en", digit_style: "latin", permissions: ["inspections.read", "master_data.read", ...(!readOnly ? ["inspections.run"] : [])],
    }});
    if (url.pathname === "/api/v1/datasets") return route.fulfill({json: [{id: "test_roll", has_video: true, roll_length_yd: 13}]});
    if (url.pathname === "/api/v1/machines") return route.fulfill({json: [{id: OLD_ID, code: "M-01", name: "Test machine", active: true}]});
    if (url.pathname === `/api/v1/inspections/${OLD_ID}/abort`) {
      requests.aborts++;
      if (fail) return route.fulfill({status: 409, json: {detail: "The inspection changed; reload and retry."}});
      aborted = true;
      return route.fulfill({json: {...item, status: "aborted"}});
    }
    if (url.pathname === "/api/v1/inspections") {
      if (request.method() === "POST") {
        requests.createdRoll = request.postDataJSON().roll_code;
        return route.fulfill({status: 201, json: {id: NEW_ID}});
      }
      return route.fulfill({json: aborted ? (url.searchParams.has("open_only") ? [] : [{...item, status: "aborted"}]) : [item]});
    }
    return route.fulfill({status: 404, json: {detail: "UI test endpoint not provided"}});
  });
  return requests;
}

for (const [locale, messages] of [["en", en], ["bn", bn]] as const) {
  test(`unfinished inspection can be cancelled and loaded again (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!},
      {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    await page.addInitScript((theme) => localStorage.setItem("te-theme", theme), locale === "bn" ? "dark" : "light");
    const requests = await mockInspections(page);
    await page.goto("/inspect");
    const open = page.getByRole("region", {name: messages.inspect.open, exact: true});
    const recent = page.getByRole("region", {name: messages.inspect.recent, exact: true});
    await expect(open.getByRole("link", {name: messages.inspect.continue, exact: true})).toBeVisible();
    await expect(recent.getByRole("button", {name: messages.live.abort, exact: true})).toBeVisible();
    await page.screenshot({path: `test-results/abort-action-${locale}.png`, fullPage: true});
    page.once("dialog", async (dialog) => {expect(dialog.message()).toContain(ROLL); await dialog.dismiss();});
    await open.getByRole("button", {name: messages.live.abort, exact: true}).click();
    expect(requests.aborts).toBe(0);
    await expect(open).toContainText(ROLL);
    page.once("dialog", (dialog) => dialog.accept());
    await open.getByRole("button", {name: messages.live.abort, exact: true}).click();
    await expect(open).not.toContainText(ROLL);
    await expect(recent).toContainText(messages.istatus.aborted);
    await expect(page.getByRole("button", {name: messages.live.abort, exact: true})).toHaveCount(0);
    await expect(page.getByTestId("roll-code")).toHaveValue(ROLL);
    await expect(page.getByTestId("roll-code")).toBeFocused();
    await page.getByTestId("load-roll").click();
    await page.waitForURL(`**/inspect/${NEW_ID}`);
    expect(requests.aborts).toBe(1);
    expect(requests.createdRoll).toBe(ROLL);
  });
}

test("read-only users cannot abort an inspection", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  const requests = await mockInspections(page, {readOnly: true});
  await page.goto("/inspect");
  await expect(page.getByRole("region", {name: en.inspect.open})).toContainText(ROLL);
  await expect(page.getByRole("button", {name: en.live.abort, exact: true})).toHaveCount(0);
  expect(requests.aborts).toBe(0);
});

test("a failed abort keeps the unfinished inspection and displays the error", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  const requests = await mockInspections(page, {fail: true});
  await page.goto("/inspect");
  const open = page.getByRole("region", {name: en.inspect.open});
  page.once("dialog", (dialog) => dialog.accept());
  await open.getByRole("button", {name: en.live.abort, exact: true}).click();
  await expect(page.getByRole("alert").filter({hasText: "The inspection changed"})).toBeVisible();
  await expect(open).toContainText(ROLL);
  await expect(open.getByRole("button", {name: en.live.abort, exact: true})).toBeEnabled();
  expect(requests.aborts).toBe(1);
});
