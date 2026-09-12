import { expect, test } from "@playwright/test";

test("tracker map focus and filters respond", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.removeItem("clear_tracker_map_state");
  });
  await page.goto("/osint?tab=trackers");
  await expect(page.getByRole("heading", { name: "Live Trackers" })).toBeVisible();
  await expect(page.getByText("Map Focus")).toBeVisible();

  const lockButton = page.getByRole("button", { name: /Lock View/i });
  const initialLockText = await lockButton.textContent();
  await lockButton.click();
  await expect(lockButton).not.toHaveText(initialLockText || "");

  const followButton = page.getByRole("button", { name: /Follow/i });
  await expect(followButton).toBeVisible();

  const flightsButton = page.getByRole("button", { name: /Flights/i }).first();
  const initialFlightsText = await flightsButton.textContent();
  await flightsButton.click();
  await expect(flightsButton).not.toHaveText(initialFlightsText || "");

  await expect(page.getByText("Operators", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /All Operators/i })).toBeVisible();

  const livePointsButton = page.getByRole("button", { name: /Live Points/i });
  const initialLivePointsText = await livePointsButton.textContent();
  await livePointsButton.click();
  await expect(livePointsButton).not.toHaveText(initialLivePointsText || "");

  const historyButton = page.getByRole("button", { name: /History Line/i });
  const initialHistoryText = await historyButton.textContent();
  await historyButton.click();
  await expect(historyButton).not.toHaveText(initialHistoryText || "");
});

test("tracker stream status explains server filters", async ({ page }) => {
  await page.goto("/osint?tab=trackers");
  const status = page.getByTestId("tracker-stream-status");
  await page.getByLabel("Country").fill("United States");
  await expect(status).toBeVisible();
  await expect(status).toContainText("Stream disabled");
  await expect(status).toContainText("Server filters are active");
});

test("tracker stream status explains pause", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("lotbook_tracker_paused", "true");
  });
  await page.goto("/osint?tab=trackers");
  await expect(page.getByTestId("tracker-stream-status")).toContainText("Stream disabled");
  await expect(page.getByTestId("tracker-stream-status")).toContainText("Tracking is paused");
});
