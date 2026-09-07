import { expect, type Locator, test } from "@playwright/test";

async function expectAnyVisible(locators: Locator[]) {
  await expect
    .poll(async () => {
      for (const locator of locators) {
        if (await locator.first().isVisible().catch(() => false)) {
          return true;
        }
      }
      return false;
    })
    .toBe(true);
}

test("advisory landing keeps World secondary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your work, in focus." })).toBeVisible();
  await expect(page.getByTestId("globe-overlay")).toHaveCount(0);
  await page.getByText("Workspace", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Open World", exact: true })).toBeVisible();
});

test("clients page renders command center with real data or safe empty state", async ({ page }) => {
  await page.goto("/clients");
  await expect(page.getByText("Portfolio Command Center")).toBeVisible();
  await expect(page.getByPlaceholder("Name, ID, risk profile...")).toBeVisible();
  await expect(page.getByRole("button", { name: "New Client" })).toBeVisible();
});

test("trackers page renders live feed controls", async ({ page }) => {
  await page.goto("/osint?tab=trackers");
  await expect(page.getByRole("heading", { name: "Live Trackers" })).toBeVisible();
  await expect(
    page.getByPlaceholder("Search flight number, operator, tail, ICAO24...")
  ).toBeVisible();
  await expect(page.getByText("Map Focus")).toBeVisible();
});

test("intel and news pages render real-data workspaces", async ({ page }) => {
  await page.goto("/osint?tab=intel");
  await expect(page.getByText("Global Impact Summary")).toBeVisible();
  await expect(page.getByText("Combined Overview")).toBeVisible();
  await expect(page.getByText("Regional Emotion Matrix")).toBeVisible();
  await expect(page.getByText("Conflict context", { exact: true })).toBeVisible();

  await page.goto("/osint?tab=news");
  await expect(page.getByText("Market Signals")).toBeVisible();
  await expect(page.locator("#news-region")).toBeVisible();
});

test("osint tabs switch", async ({ page }) => {
  await page.goto("/osint?tab=trackers");
  await expect(page.getByRole("heading", { name: "Live Trackers" })).toBeVisible();
  await page.getByRole("tab", { name: /Signals/ }).click();
  await expect(page.getByText("Global Impact Summary")).toBeVisible();
  await page.getByRole("tab", { name: /News/ }).click();
  await expect(page.getByText("Market Signals")).toBeVisible();
});

test("tracker globe entry opens the overview globe with layer controls", async ({ page }) => {
  await page.goto("/osint?tab=trackers");
  await page.getByTestId("osint-open-globe").click();
  const overlay = page.getByTestId("globe-overlay");
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole("heading", { name: "World" })).toBeVisible();
  await expect(page.getByTestId("globe-bottom-inspector")).toContainText(
    "Select an object to inspect it"
  );
  await expect(page.getByText("Scene Status")).toHaveCount(0);
  await page.getByTestId("globe-controls-toggle").click();
  await expect(page.getByText("Scene Status")).toBeVisible();
  await expect(page.getByTestId("globe-layer-trackers")).toBeVisible();
  await expect(page.getByTestId("globe-layer-regions")).toBeVisible();
  await page.getByTestId("globe-layer-regions").click();
  await expect(page.getByTestId("globe-layer-regions")).toBeVisible();
  await page.getByTestId("globe-layer-regions").click();
  await page.getByTestId("globe-browse-toggle").click();
  await expect(page.getByText("Operational Focus")).toBeVisible();
  await expectAnyVisible([
    page.getByTestId("globe-preset-free"),
    page.getByText("Unavailable", { exact: true })
  ]);
  await expectAnyVisible([
    page.getByText("Visible Aggregate"),
    page.getByText("Unavailable", { exact: true })
  ]);
  await expectAnyVisible([
    page.getByRole("button", { name: "Refresh Scene" }),
    page.getByRole("button", { name: "Retry Scene" })
  ]);
  await expect(page.getByLabel("Collapse context panel")).toBeVisible();
  await page.getByLabel("Collapse context panel").click();
  await expect(page.getByLabel("Expand context panel")).toBeVisible();
  await page.getByLabel("Expand context panel").click();
  await expect(page.getByLabel("Collapse context panel")).toBeVisible();
  await page.getByLabel("Close world view").click();
  await expect(overlay).toHaveCount(0);
});

test("intel globe overlay opens with regional scene controls", async ({ page }) => {
  await page.goto("/osint?tab=intel");
  await page.getByTestId("osint-open-globe").click();
  await expect(page.getByTestId("globe-overlay")).toBeVisible();
  await page.getByTestId("globe-controls-toggle").click();
  await page.getByTestId("globe-browse-toggle").click();
  await expectAnyVisible([
    page.getByText("Operational Focus", { exact: true }),
    page.getByRole("button", { name: "Retry Scene" })
  ]);
  await expectAnyVisible([
    page.getByTestId("globe-lens-emotion"),
    page.getByText("Unavailable", { exact: true })
  ]);
  await expect(page.getByTestId("globe-layer-hotspots")).toBeVisible();
  await expectAnyVisible([
    page.getByText("Visible Aggregate"),
    page.getByText("Unavailable", { exact: true })
  ]);
  await expectAnyVisible([
    page.getByText("Visible Centroid Highlights"),
    page.getByText("Unavailable", { exact: true })
  ]);
});

test("globe overlay closes with Escape", async ({ page }) => {
  await page.goto("/osint?tab=trackers");
  await page.getByTestId("osint-open-globe").click();
  await expect(page.getByTestId("globe-overlay")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("globe-overlay")).toHaveCount(0);
});
