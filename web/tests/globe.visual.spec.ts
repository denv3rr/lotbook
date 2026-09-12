import { expect, test } from "@playwright/test";
import { loadCapturedIntelGlobeFixture } from "./fixtures/globeFixtures";

test.describe("globe fail-safe visual regression", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("tracker globe unavailable state matches snapshot", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route("**/api/osint/scene/overview**", async (route) => {
      await route.abort();
    });
    await page.route("**/api/osint/scene/trackers**", async (route) => {
      await route.abort();
    });
    await page.route("**/api/trackers/snapshot**", async (route) => {
      await route.abort();
    });
    await page.goto("/osint?tab=trackers");
    await page.getByTestId("osint-open-globe").click();
    await page.getByTestId("globe-scene-trackers").click();
    await expect(page.getByTestId("globe-overlay")).toBeVisible();
    await expect(page.getByTestId("globe-overlay").getByText("Unavailable", { exact: true })).toBeVisible();
    await expect(
      page.getByTestId("globe-overlay").getByText(
        "The immersive scene could not be recovered. Retry or close the overlay."
      )
    ).toBeVisible();
    await expect(page.getByTestId("globe-overlay")).toHaveScreenshot(
      "tracker-globe-unavailable.png",
      {
        animations: "disabled",
        caret: "hide",
        maxDiffPixels: 20,
        scale: "css"
      }
    );
  });

  test("intel globe unavailable state matches snapshot", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route("**/api/osint/scene/overview**", async (route) => {
      await route.abort();
    });
    await page.route("**/api/osint/scene/intel**", async (route) => {
      await route.abort();
    });
    await page.goto("/osint?tab=intel");
    await page.getByTestId("osint-open-globe").click();
    await page.getByTestId("globe-scene-intel").click();
    await expect(page.getByTestId("globe-overlay")).toBeVisible();
    await expect(page.getByTestId("globe-overlay").getByText("Unavailable", { exact: true })).toBeVisible();
    await expect(
      page.getByTestId("globe-overlay").getByText(
        "The immersive scene could not be recovered. Retry or close the overlay."
      )
    ).toBeVisible();
    await expect(page.getByTestId("globe-overlay")).toHaveScreenshot(
      "intel-globe-unavailable.png",
      {
        animations: "disabled",
        caret: "hide",
        maxDiffPixels: 20,
        scale: "css"
      }
    );
  });

  test("intel globe loaded state matches captured real fixture snapshot", async ({ page }) => {
    const fixture = loadCapturedIntelGlobeFixture();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript((sceneState) => {
      window.localStorage.setItem("lotbook_scene_state", JSON.stringify(sceneState));
    }, {
      version: 2,
      cameraPreset: "focus",
      intelCategories: ["conflict"],
      intelIndustry: "all",
      intelLens: "conflict",
      intelSources: [],
      trackerCategory: "all",
      trackerCountry: "",
      trackerMode: "combined",
      trackerOperator: "",
      detailsVisible: true,
      showIntelHotspots: true,
      showIntelRegions: true,
      showTrackerPoints: true,
      showTrackerTrails: true,
    });
    await page.route("**/api/osint/scene/overview**", async (route) => {
      await route.abort();
    });
    await page.route("**/api/osint/scene/intel**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture.scene_payload),
      });
    });
    await page.route("**/api/intel/meta**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture.intel_meta_payload),
      });
    });
    await page.goto("/osint?tab=intel");
    await page.getByTestId("osint-open-globe").click();
    await page.getByTestId("globe-scene-intel").click();
    await expect(page.getByTestId("globe-overlay")).toBeVisible();
    await expect(page.getByTestId("globe-overlay")).toContainText("Visible Regions");
    await expect(page.getByTestId("globe-overlay")).toContainText("Coordinates");
    await expect(
      page.getByTestId("globe-overlay").getByText(
        "The immersive scene could not be recovered. Retry or close the overlay."
      )
    ).toHaveCount(0);
    await expect(page.getByTestId("globe-overlay")).toHaveScreenshot(
      "intel-globe-loaded-real-fixture.png",
      {
        animations: "disabled",
        caret: "hide",
        maxDiffPixels: 40,
        scale: "css"
      }
    );
  });

  test("legacy hidden scene state migrates to visible signals", async ({ page }) => {
    const fixture = loadCapturedIntelGlobeFixture();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(() => {
      window.localStorage.setItem("lotbook_scene_state", JSON.stringify({
        cameraPreset: "free",
        intelCategories: ["stale-filter"],
        intelIndustry: "all",
        intelLens: "combined",
        intelSources: ["stale-source"],
        trackerCategory: "all",
        trackerCountry: "",
        trackerMode: "combined",
        trackerOperator: "",
        detailsVisible: false,
        showIntelHotspots: false,
        showIntelRegions: false,
        showTrackerPoints: false,
        showTrackerTrails: false,
      }));
    });
    await page.route("**/api/osint/scene/overview**", async (route) => {
      await route.abort();
    });
    await page.route("**/api/osint/scene/intel**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture.scene_payload),
      });
    });
    await page.route("**/api/intel/meta**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture.intel_meta_payload),
      });
    });
    await page.goto("/osint?tab=intel");
    await page.getByTestId("osint-open-globe").click();
    await page.getByTestId("globe-scene-intel").click();
    await expect(page.getByTestId("globe-overlay")).toContainText("6 regional signals");
    await expect(page.getByTestId("globe-show-available-layers")).toHaveCount(0);
    await page.getByTestId("globe-controls-toggle").click();
    await expect(page.getByTestId("globe-layer-regions")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("globe-layer-hotspots")).toHaveAttribute("aria-pressed", "true");
    const storedState = await page.evaluate(() =>
      JSON.parse(window.localStorage.getItem("lotbook_scene_state") || "{}")
    );
    expect(storedState).toMatchObject({
      version: 2,
      intelCategories: [],
      intelSources: [],
      showIntelHotspots: true,
      showIntelRegions: true,
    });
  });
});
