import { expect, test, type Locator, type Page } from "@playwright/test";

async function openAssistant(page: Page) {
  const assistantVisible = page.locator("button:visible", {
    hasText: "Assistant"
  });
  if ((await assistantVisible.count()) === 0) {
    await page.getByText("Workspace", { exact: true }).click();
  }
  await expect(assistantVisible.first()).toBeVisible();
  await assistantVisible.first().click();
  await expect(page.getByRole("heading", { name: "AI Assistant" })).toBeVisible();
  await expect(page.locator("div.fixed.inset-y-0.right-0.z-50")).toBeVisible();
}

function assistantDrawer(page: Page) {
  return page.locator("div.fixed.inset-y-0.right-0.z-50");
}

function assistantContextInput(drawer: Locator, label: string) {
  return drawer
    .locator("label", { hasText: label })
    .locator("xpath=following-sibling::input[1]");
}

test("assistant sends real context and renders backend response", async ({ page }) => {
  let requestBody: Record<string, unknown> | null = null;
  let requestHeaders: Record<string, string> | null = null;

  await page.route("**/api/assistant/query", async (route) => {
    const request = route.request();
    requestBody = request.postDataJSON() as Record<string, unknown>;
    requestHeaders = request.headers();
    await route.continue();
  });

  await page.goto("/osint?tab=news");
  await openAssistant(page);
  const drawer = assistantDrawer(page);

  await assistantContextInput(drawer, "Region").fill("Global");
  await assistantContextInput(drawer, "Industry").fill("all");
  await assistantContextInput(drawer, "Tickers").fill("AAPL, MSFT");
  await assistantContextInput(drawer, "Sources").fill("cnbc.com");

  const questionInput = drawer.getByPlaceholder("Ask a question...");
  await questionInput.fill("latest news");
  await questionInput.press("Enter");

  await expect(drawer.getByText("latest news")).toBeVisible();
  await expect(drawer).toContainText("Routing: news (handle_news)");
  await expect(drawer).toContainText("Sources: /api/intel/news");

  expect(requestHeaders?.["x-api-key"]).toBeTruthy();
  expect(requestBody?.question).toBe("latest news");
  expect(requestBody?.context).toMatchObject({
    region: "Global",
    industry: "all",
    tickers: ["AAPL", "MSFT"]
  });
  expect(requestBody?.sources).toEqual(["cnbc.com"]);
});

test("assistant context scope persists across pages", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem(
      "clear.assistant.context",
      JSON.stringify({ clientId: "client-1", accountId: "acct-1" })
    );
  });

  await page.goto("/clients");
  await expect
    .poll(() =>
      page.evaluate(() => window.localStorage.getItem("clear.assistant.context"))
    )
    .toContain("client-1");

  await page.goto("/trackers");
  await expect
    .poll(() =>
      page.evaluate(() => window.localStorage.getItem("clear.assistant.context"))
    )
    .toContain("acct-1");
});

test("assistant surfaces auth failures", async ({ page }) => {
  await page.route("**/api/assistant/query", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unauthorized" })
    });
  });

  await page.goto("/system");
  await openAssistant(page);
  const drawer = assistantDrawer(page);

  const questionInput = drawer.getByPlaceholder("Ask a question...");
  await questionInput.fill("Status?");
  await questionInput.press("Enter");

  await expect(
    drawer.getByText("Error: Could not connect to the AI assistant.")
  ).toBeVisible();
});
