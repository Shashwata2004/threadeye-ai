import { expect, test, type Page } from "@playwright/test";
import en from "../messages/en.json";
import bn from "../messages/bn.json";

const id = "00000000-0000-4000-8000-000000000004";
const root = `/api/v1/inspections/${id}`;
async function mock(page: Page, failDecision = false) {
  let selection = "buyer", approved = false;
  const state = {decisions: 0, selections: 0};
  const snapshot = {id, roll_id: id, roll_code: "TE-000004", status: "completed", finalized_at: "2026-11-03T12:00:00Z",
    system_verdict: "BORDERLINE", final_verdict: null as string | null, decision_reason: null as string | null,
    decision_by: null as string | null, points_total: 8, points_per_100: 38.07, yards_inspected: 13,
    unreviewed: 0, provider: {display_name: "Test AI", is_simulated: false},
    roll: {roll_code: "TE-000004", challan_no: "DEMO", supplier: "Sample Mill", buyer: "Sample Buyer",
      rule_profile: "Default 4-point", lot_id: id, threshold_per_100: 40}};
  const cutting = () => ({inspection_id: id, source_hash: selection, status: approved ? "approved" : "draft",
    simulated: true, policy_selection: selection, policy_locked: approved, fabric: null, defects: [],
    plan: {length_yd: 13, usable_yd: selection === "all" ? 12 : 13, skipped_yd: selection === "all" ? 1 : 0,
      segments: selection === "all" ? [{start_yd: 0, end_yd: 12, action: "keep"}, {start_yd: 12, end_yd: 13, action: "skip"}]
        : [{start_yd: 0, end_yd: 13, action: "keep"}],
      policy: {margin_in: 2, min_piece_yd: 1, min_points_to_cut: selection === "all" ? 1 : 2}}});
  await page.route("**/health", route => route.fulfill({json: {status: "ok", db: "ok", simulated_mode: false}}));
  await page.route("**/api/**", async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path === "/api/v1/auth/me") return route.fulfill({json: {id, username: "supervisor", role: "qc_supervisor", display_name: "Test supervisor", locale: "en", digit_style: "latin", permissions: ["inspections.read", "verdict.decide", "cutting.read", "cutting.approve"]}});
    if (path === root) return route.fulfill({json: snapshot});
    if (path === root + "/defects") return route.fulfill({json: []});
    if (path === root + "/decision") {
      state.decisions++;
      if (failDecision) return route.abort("failed");
      snapshot.final_verdict = req.postDataJSON().final_verdict;
      snapshot.decision_reason = req.postDataJSON().reason;
      snapshot.decision_by = "Test supervisor";
      return route.fulfill({json: snapshot});
    }
    if (path === root + "/cutting/policy") {selection = req.postDataJSON().selection; state.selections++; return route.fulfill({json: cutting()});}
    if (path === root + "/cutting/approve") {approved = true; return route.fulfill({json: cutting()});}
    if (path === root + "/cutting") return route.fulfill({json: cutting()});
    return route.fulfill({status: 404, json: {detail: "mock endpoint unavailable"}});
  });
  return state;
}

for (const [locale, messages] of [["en", en], ["bn", bn]] as const) {
  test(`cutting policy autosaves and a signed decision survives returning (${locale})`, async ({page, context, baseURL}) => {
    await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: locale, url: baseURL!}]);
    await page.addInitScript(theme => localStorage.setItem("te-theme", theme), locale === "bn" ? "dark" : "light");
    const state = await mock(page);
    await page.goto(`/inspections/${id}`);
    const decision = page.getByTestId("decision");
    const reason = decision.getByRole("textbox");
    await decision.getByRole("radio", {name: messages.verdicts.ACCEPT, exact: true}).check();
    await reason.fill("Accept with defect-aware cutting instructions");
    const toCutting = page.getByRole("link", {name: locale === "bn" ? "কাটিং নির্দেশনা" : "Cutting sheet", exact: true});
    await toCutting.click();
    const policy = page.getByRole("combobox", {name: locale === "bn" ? "কাটিং নীতি" : "Cutting policy", exact: true});
    await expect(policy).toHaveValue("buyer");
    await policy.selectOption("all");
    await expect(policy).toHaveValue("all");
    await expect(page.getByTestId("skip-overlay")).toHaveCount(1);
    expect(state.selections).toBe(1);
    const back = page.getByRole("link", {name: locale === "bn" ? "পরীক্ষায় ফিরুন" : "Back to inspection", exact: true});
    await back.click();
    await expect(reason).toHaveValue("Accept with defect-aware cutting instructions");
    await expect(decision.getByRole("radio", {name: messages.verdicts.ACCEPT, exact: true})).toBeChecked();
    await decision.getByRole("button", {name: messages.verdict.decide, exact: true}).click();
    await expect(reason).toBeDisabled();
    await expect(reason).toHaveValue("Accept with defect-aware cutting instructions");
    await expect(page.getByTestId("decision-locked")).toBeVisible();
    await toCutting.click();
    await expect(policy).toHaveValue("all");
    await page.getByRole("button", {name: locale === "bn" ? "কাটিং অনুমোদন" : "Approve cutting plan", exact: true}).click();
    await expect(policy).toBeDisabled();
    await back.click();
    await expect(page).toHaveURL(`/inspections/${id}`);
    await expect(reason).toBeVisible();
    await page.reload();
    await expect(reason).toHaveValue("Accept with defect-aware cutting instructions");
    await expect(reason).toBeDisabled();
    await expect(decision.getByRole("radio", {name: messages.verdicts.ACCEPT, exact: true})).toBeChecked();
    await expect(decision.getByRole("button")).toHaveCount(0);
    expect(state.decisions).toBe(1);
    await page.screenshot({path: `test-results/decision-locked-${locale}.png`, fullPage: true});
  });
}

test("a failed decision request keeps an editable draft after reload", async ({page, context, baseURL}) => {
  await context.addCookies([{name: "te_session", value: "ui-test", url: baseURL!}, {name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  await mock(page, true);
  await page.goto(`/inspections/${id}`);
  const decision = page.getByTestId("decision"), reason = decision.getByRole("textbox");
  await reason.fill("Preserve this unsaved reason");
  await decision.getByRole("button", {name: en.verdict.decide, exact: true}).click();
  await expect(decision).toContainText(en.verdict.saveError);
  await expect(reason).toBeEnabled();
  await page.reload();
  await expect(reason).toHaveValue("Preserve this unsaved reason");
  await expect(reason).toBeEnabled();
});
