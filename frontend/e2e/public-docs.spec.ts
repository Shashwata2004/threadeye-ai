import { expect, test } from "@playwright/test";

test("public docs, admin edits and unpublishing", async ({
  page,
  context,
  baseURL,
}) => {
  await context.addCookies([{name: "NEXT_LOCALE", value: "en", url: baseURL!}]);
  const c = {
    revision: 0,
    enabled: true,
    project_name: "Fixture docs",
    team_name: "DU_Synapse",
    tagline: { en: "Fixture overview", bn: "পরিচিতি" },
    repository_url: "https://github.com/Shashwata2004/threadeye-ai",
    app_url: "https://threadeye-web.vercel.app",
    video_url: "https://youtu.be/dFBMcYwV3NI",
    starts_at: null,
    ends_at: null,
    show_live: true,
    show_team: true,
    show_apis: true,
    sections: [
      {
        id: "problem",
        title: { en: "Problem", bn: "সমস্যা" },
        body: { en: "Traceable fabric inspection", bn: "কাপড় পরীক্ষা" },
        visible: true,
        diagram: "architecture",
        steps: ["Browser", "API", "Database", "Detector"].map(en => ({en,bn:en})),
      },
    ],
    members: [],
  };
  await page.route("**/api/**", async (r) => {
    const p = new URL(r.request().url()).pathname;
    if (p.endsWith("/auth/me"))
      return r.fulfill({
        json: {
          id: "fixture",
          username: "admin",
          role: "admin",
          display_name: "Admin",
          permissions: ["settings.manage"],
          locale: "en",
        },
      });
    if (p.endsWith("/documentation/admin")) {
      if (r.request().method() === "PUT") {
        Object.assign(c, r.request().postDataJSON());
        c.revision++;
      }
      return r.fulfill({ json: c });
    }
    if (p.endsWith("/documentation") || p.endsWith("/documentation/preview"))
      return c.enabled || p.endsWith("preview")
        ? r.fulfill({ json: { content: c, live: null, apis: [] } })
        : r.fulfill({ status: 404, json: { detail: "unpublished" } });
    return r.fulfill({ status: 404, json: { detail: "fixture" } });
  });
  const background = await page.request.get("/images/docs-garment-factory.webp");
  expect(background.status()).toBe(200);
  expect(background.headers()["content-type"]).toContain("image/webp");
  await page.goto("/docs");
  await expect(
    page.getByRole("heading", { name: "Fixture docs", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Presentation video" }),
  ).toHaveAttribute("href", c.video_url);
  await expect(page.getByRole("img", {name:"Problem"}).getByRole("listitem")).toHaveCount(4);
  await page.setViewportSize({width:390,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.addCookies([
    { name: "te_session", value: "fixture", url: baseURL! },
  ]);
  await page.goto("/admin/docs");
  await page.getByLabel("project name", { exact: true }).fill("Updated docs");
  await page.getByRole("button", { name: "Save documentation" }).click();
  await expect(page.getByRole("status").filter({hasText:"Saved"})).toContainText("Saved");
  await page.goto("/docs");
  await expect(
    page.getByRole("heading", { name: "Updated docs", exact: true }),
  ).toBeVisible();
  await page.goto("/admin/docs");
  await page.getByLabel("Publicly available").uncheck();
  await page.getByRole("button", { name: "Save documentation" }).click();
  await expect(page.getByRole("status").filter({hasText:"Saved"})).toContainText("Saved");
  await page.goto("/docs");
  await expect(
    page.getByRole("heading", { name: "Documentation unavailable" }),
  ).toBeVisible();
  await expect(page.getByText("Traceable fabric inspection")).toHaveCount(0);
});
