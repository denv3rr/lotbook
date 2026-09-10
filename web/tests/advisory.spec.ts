import { expect, test } from "@playwright/test";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { loadCapturedIntelGlobeFixture } from "./fixtures/globeFixtures";
import { AREA_STORAGE_KEY, areaGeometry, basemapSourceLabel, centeredMercatorZoom, coordinateBounds, isImageryError, projectionForZoom, readAreas, sceneCameraTarget } from "../src/lib/worldMap";

test.describe.configure({ mode: "serial" });

test("advisory landing, real client and mandate workflow, keyboard dialog", async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", error => failures.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your work, in focus." })).toBeVisible();
  await expect(page.locator(".globe-overlay")).toHaveCount(0);
  await page.getByRole("button", { name: "Add your first client" }).click();
  const dialog = page.getByRole("dialog", { name: "New client" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.locator(":focus")).toHaveCount(1);
  await dialog.getByLabel("Client or company name").fill("Clear browser verification");
  await dialog.getByRole("button", { name: "Save client" }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "New deal", exact: true }).first().click();
  const deal = page.getByRole("dialog", { name: "New deal" });
  await deal.getByRole("combobox", { name: "Client *", exact: true }).selectOption({ label: "Clear browser verification" });
  await deal.getByLabel("Deal name").fill("Advisory workflow verification");
  await deal.getByLabel("Deal owner").fill("Verification operator");
  await deal.getByLabel("Source / basis").fill("Operator-created acceptance record in an isolated database; no client or market facts claimed.");
  await deal.getByLabel("Next action").fill("Verify client handoff");
  await deal.getByRole("button", { name: "Save deal" }).click();
  await expect(page.getByRole("button", { name: "Advisory workflow verification" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Verify client handoff", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Advisory workflow verification" }).click();
  await page.getByRole("dialog").getByRole("combobox", { name: "Stage", exact: true }).selectOption("mandated");
  await page.getByRole("button", { name: "Save deal" }).click();
  await expect(page.locator("tbody").getByText("Mandated", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("prospect → mandated");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Tasks & diligence" }).click();
  await page.getByRole("button", { name: "New task" }).click();
  const task = page.getByRole("dialog");
  await task.getByRole("combobox", { name: "Client *", exact: true }).selectOption({ label: "Clear browser verification" });
  await task.getByLabel("Task title").fill("Verify review workflow");
  await task.getByLabel("Task owner").fill("Verification operator");
  await task.getByLabel("Source / basis").fill("Actual isolated browser acceptance run.");
  await task.getByRole("button", { name: "Save task" }).click();
  await page.getByRole("button", { name: "Complete Verify review workflow" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Relationships", exact: true }).click();
  await page.getByRole("button", { name: "New contact" }).click();
  const contact = page.getByRole("dialog");
  await contact.getByRole("combobox", { name: "Client *", exact: true }).selectOption({ label: "Clear browser verification" });
  await contact.getByLabel("Contact name").fill("Acceptance operator");
  await contact.getByLabel("Relationship owner").fill("Verification operator");
  await contact.getByLabel("Source / basis").fill("Actual isolated acceptance run; not a customer contact.");
  await contact.getByRole("button", { name: "Save contact" }).click();
  await expect(page.getByRole("heading", { name: "Acceptance operator" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export", exact: true }).click();
  expect((await download).suggestedFilename()).toContain("clear-advisory");
  await page.getByRole("button", { name: "Deal pipeline", exact: true }).click();
  await page.screenshot({ path: "test-results/advisory-desktop.png", fullPage: true });
  expect(failures).toEqual([]);
});

test("arithmetic-only DCF and comparable models save, reload, and preserve versions through real API", async ({ page }) => {
  await page.goto("/valuation");
  const source = "Deterministic arithmetic acceptance inputs only, not a company valuation or market evidence.";
  await page.getByLabel("Valuation date").fill("2026-01-01");
  await page.getByLabel("Sources and assumption basis").fill(source);
  await page.getByLabel("Year 1 FCFF").fill("100");
  await page.getByLabel("WACC (%)").fill("10");
  await page.getByLabel("Terminal growth (%)").fill("0");
  for (const name of ["cash", "debt", "other_claims", "non_operating_assets"]) await page.locator(`input[name="${name}"]`).fill("0");
  await page.getByRole("button", { name: "Calculate valuation", exact: true }).click();
  await expect(page.locator(".bank-value").first()).toHaveText("$1,000.00");
  await page.getByLabel("Model name").fill("DCF arithmetic snapshot");
  await page.getByLabel("Prepared by").fill("Acceptance operator");
  await page.getByRole("combobox", { name: "Model client *", exact: true }).selectOption({ label: "Clear browser verification" });
  await page.getByRole("button", { name: "Save model version" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Valuation saved" })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Load assumptions" }).click();
  await expect(page.getByLabel("Year 1 FCFF")).toHaveValue("100");
  await page.getByRole("button", { name: "Calculate valuation", exact: true }).click();
  await page.getByLabel("Model name").fill("DCF arithmetic revision");
  await page.getByLabel("Prepared by").fill("Acceptance operator");
  await page.getByRole("button", { name: "Save model version" }).click();
  await expect(page.getByRole("cell", { name: "Revised snapshot", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Comparable companies", exact: true }).click();
  await page.getByLabel("Observation date").fill("2026-01-01");
  await page.locator('textarea[name="source_note"]').fill(source);
  for (const name of ["cash", "debt", "other_claims", "non_operating_assets"]) await page.locator(`input[name="${name}"]`).fill("0");
  await page.getByLabel("Target revenue").fill("200");
  await page.getByLabel("Target EBITDA").fill("20");
  await page.getByLabel("Peer 1 name").fill("Arithmetic acceptance peer");
  await page.getByLabel("Peer 1 enterprise value").fill("1000");
  await page.getByLabel("Peer 1 revenue").fill("100");
  await page.getByLabel("Peer 1 ebitda").fill("10");
  await page.getByLabel("Peer 1 source note").fill(source);
  await page.getByRole("button", { name: "Calculate comparables", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Peer multiples & implied value" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "$2,000.00", exact: true }).first()).toBeVisible();
  await page.getByLabel("Model name").fill("Comparable arithmetic snapshot");
  await page.getByLabel("Prepared by").fill("Acceptance operator");
  await page.getByRole("combobox", { name: "Model client *", exact: true }).selectOption({ label: "Clear browser verification" });
  await page.getByRole("button", { name: "Save model version" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Valuation saved" })).toBeVisible();
});

test("mobile layout, World menu and valuation validation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/valuation");
  await expect(page.getByRole("heading", { name: "Understand the value drivers." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByText("Workspace", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Open World", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Calculate valuation" }).click();
  await expect(page.locator("input:invalid").first()).toBeVisible();
  await page.screenshot({ path: "test-results/advisory-mobile.png", fullPage: true });
});

test("client profile loads independently and hidden pattern analysis stays idle", async ({ page, request }) => {
  const api = "http://127.0.0.1:18080";
  const headers = { "X-API-Key": "isolated-browser-verification" };
  const indexResponse = await request.get(`${api}/api/clients`, { headers });
  expect(indexResponse.ok()).toBeTruthy();
  const client = (await indexResponse.json()).clients.find((row: { name: string }) => row.name === "Clear browser verification");
  expect(client).toBeTruthy();
  const accountResponse = await request.post(`${api}/api/clients/${client.client_id}/accounts`, { headers, data: { account_name: "Isolated loading verification", account_type: "Taxable", holdings: {} } });
  expect(accountResponse.ok(), await accountResponse.text()).toBeTruthy();
  const account = (await accountResponse.json()).account;
  const profilePath = `/api/clients/${client.client_id}`;
  const observed: string[] = [];
  const failures: string[] = [];
  page.on("request", req => observed.push(new URL(req.url()).pathname));
  page.on("pageerror", error => failures.push(error.message));
  await page.goto(`/clients?client=${encodeURIComponent(client.client_id)}`);
  await expect(page.getByRole("button", { name: /Client Profile Clear browser verification/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh snapshot", exact: true })).toBeEnabled();
  expect(observed.filter(url => url.endsWith("/patterns"))).toEqual([]);
  await expect(page.getByText("Return History Surface", { exact: true })).toHaveCount(0);
  const profileLoads = observed.filter(url => url === profilePath).length;
  const accountDashboard = page.waitForResponse(response => new URL(response.url()).pathname === `${profilePath}/accounts/${account.account_id}/dashboard`);
  await page.getByLabel("Portfolio scope").selectOption(account.account_id);
  await accountDashboard;
  await expect(page.getByRole("button", { name: "Refresh snapshot", exact: true })).toBeEnabled();
  expect(observed.filter(url => url === profilePath)).toHaveLength(profileLoads);
  expect(observed.filter(url => url.endsWith("/patterns"))).toEqual([]);
  const patternRequest = page.waitForRequest(req => new URL(req.url()).pathname.endsWith("/patterns"));
  await page.getByRole("button", { name: /Pattern Analysis Load on demand/ }).click();
  await patternRequest;
  await expect(page.getByText("Realtime valuations active.", { exact: true })).toHaveCount(0);
  expect(failures).toEqual([]);
});

test("research-area geometry handles antimeridian and rejects invalid storage", () => {
  expect(coordinateBounds([[179, -10], [-179, 10]])).toEqual([179, -10, -179, 10]);
  const geometry = areaGeometry([179, -10, -179, 10]);
  expect(geometry.type).toBe("MultiPolygon");
  expect(geometry.coordinates).toHaveLength(2);
  expect(() => areaGeometry([0, 20, 5, -20])).toThrow();
  expect(() => readAreas('[{"name":"invalid"}]')).toThrow();
  expect(isImageryError({ sourceId: "imagery" })).toBe(true);
  expect(isImageryError({ sourceId: "detail" })).toBe(true);
  expect(isImageryError({ sourceId: "street" })).toBe(true);
  for (const url of ["https://gibs.earthdata.nasa.gov.evil.invalid/tile", "https://evil.invalid/gibs.earthdata.nasa.gov", "https://gibs.earthdata.nasa.gov@evil.invalid/tile"]) {
    expect(isImageryError({ sourceId: "observations", error: { message: url } } as { sourceId: string })).toBe(false);
  }
  expect(sceneCameraTarget({ target_lat: NaN, target_lon: 10 })).toBeNull();
  expect(sceneCameraTarget({ target_lat: 100, target_lon: 10 })).toBeNull();
  expect(sceneCameraTarget(loadCapturedIntelGlobeFixture().scene_payload.camera_defaults)).toEqual([7.2, 17.5]);
  expect(centeredMercatorZoom([0, 0], 512, 1024)).toBeCloseTo(1, 10);
  expect(centeredMercatorZoom([180, 90], 390, 844)).toBe(19);
  expect(basemapSourceLabel(3, "satellite")).toContain("Blue Marble");
  expect(basemapSourceLabel(14, "satellite")).toContain("Esri");
  expect(basemapSourceLabel(14, "street")).toBe("OpenStreetMap");
  expect(projectionForZoom("globe", 4)).toBe("globe");
  expect(projectionForZoom("globe", 14)).toBe("mercator");
  expect(projectionForZoom("mercator", 4)).toBe("mercator");
});

test("area vault authenticates, migrates and refuses stale or cancelled writes", async ({ page }) => {
  await page.goto("/");
  const bounds = loadCapturedIntelGlobeFixture().scene_payload.bounds;
  const result = await page.evaluate(async ({ storageKey, bounds }) => {
    const { openAreaVault, saveAreaVault, areaStorageState } = await import("/src/lib/researchAreaVault.ts");
    const pass = "isolated-area-vault-passphrase";
    const live = () => true;
    const rejects = async (operation: () => Promise<unknown>) => { try { await operation(); return false; } catch { return true; } };
    const area = { id: crypto.randomUUID(), name: "Captured context bounds roundtrip", bounds: [bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat], basis: "operator-viewport", createdAt: new Date().toISOString() };
    const created = await openAreaVault(pass, false, live);
    const saved = await saveAreaVault(created, [area], live);
    const unlocked = await openAreaVault(pass, false, live);
    const checks: Record<string, boolean> = {
      noPlaintext: !saved.raw.includes(area.name) && !saved.raw.includes("bounds") && !saved.raw.includes(pass),
      nonextractable: !saved.key.extractable,
      roundtrip: JSON.stringify(unlocked.areas) === JSON.stringify([area]),
      wrongPass: await rejects(() => openAreaVault("incorrect-passphrase", false, live)),
      wrongPassUnchanged: localStorage.getItem(storageKey) === saved.raw,
      cancelled: await rejects(() => saveAreaVault(saved, [], () => false)),
      cancelledUnchanged: localStorage.getItem(storageKey) === saved.raw,
    };
    await navigator.locks.request(storageKey, async () => { checks.lockedWriter = await rejects(() => saveAreaVault(saved, [], live)); });
    const outcomes = await Promise.allSettled([saveAreaVault(saved, [], live), saveAreaVault(unlocked, [area], live)]);
    checks.concurrent = outcomes.filter(item => item.status === "fulfilled").length === 1 && outcomes.filter(item => item.status === "rejected").length === 1;
    const latest = await openAreaVault(pass, false, live);
    checks.freshNonce = JSON.parse(latest.raw).iv !== JSON.parse(saved.raw).iv;
    const removed = await saveAreaVault(latest, [], live);
    checks.removalEncrypted = areaStorageState(removed.raw) === "locked" && (await openAreaVault(pass, false, live)).areas.length === 0;
    const corrupted = JSON.parse(saved.raw);
    corrupted.ciphertext = (corrupted.ciphertext[0] === "A" ? "B" : "A") + corrupted.ciphertext.slice(1);
    const damaged = JSON.stringify(corrupted);
    localStorage.setItem(storageKey, damaged);
    checks.tamper = await rejects(() => openAreaVault(pass, false, live));
    checks.tamperUnchanged = localStorage.getItem(storageKey) === damaged;
    localStorage.setItem(storageKey, '[{"name":"invalid"}]');
    checks.invalidLegacy = await rejects(() => openAreaVault(pass, true, live));
    const legacy = JSON.stringify([area]);
    localStorage.setItem(storageKey, legacy);
    checks.explicitMigration = await rejects(() => openAreaVault(pass, false, live));
    checks.legacyUnchanged = localStorage.getItem(storageKey) === legacy;
    const originalSet = Storage.prototype.setItem;
    Storage.prototype.setItem = function () { throw new DOMException("Storage denied", "QuotaExceededError"); };
    try { checks.storageDenied = await rejects(() => openAreaVault(pass, true, live)); }
    finally { Storage.prototype.setItem = originalSet; }
    checks.failedMigrationUnchanged = localStorage.getItem(storageKey) === legacy;
    const migrated = await openAreaVault(pass, true, live);
    checks.migrated = areaStorageState(migrated.raw) === "locked" && JSON.stringify(migrated.areas) === legacy && !migrated.raw.includes(area.name);
    return checks;
  }, { storageKey: AREA_STORAGE_KEY, bounds });
  for (const [check, passed] of Object.entries(result)) expect(passed, check).toBe(true);
});

for (const denied of ["missing", "throwing", "constructor-denied"]) {
  test(`Trackers activates real Leaflet when WebGL 2 is ${denied}`, async ({ page }) => {
    await page.addInitScript(mode => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (kind: string, ...args: unknown[]) {
        if (kind === "webgl2" && (mode !== "constructor-denied" || this.classList.contains("maplibregl-canvas"))) { if (mode === "throwing") throw new Error("GPU context denied"); return null; }
        return original.apply(this, [kind, ...args] as never);
      } as typeof original;
    }, denied);
    await page.goto("/osint?tab=trackers");
    await expect(page.locator(".leaflet-container")).toBeVisible();
    await expect(page.locator(".leaflet-control-zoom-in")).toBeVisible();
    await expect(page.locator(".maplibregl-canvas")).toHaveCount(0);
    await page.locator(".leaflet-control-zoom-in").click();
    await expect(page.getByText("WebGL 2 is not supported in this browser. Use the fallback map.", { exact: true })).toHaveCount(0);
  });
}

test("World classifies real NASA request failures without losing navigation", async ({ page }) => {
  test.setTimeout(45000);
  await page.route("https://gibs.earthdata.nasa.gov/**", route => route.abort("failed"));
  await page.goto("/");
  await page.getByText("Workspace", { exact: true }).click();
  await page.getByRole("button", { name: "Open World", exact: true }).click();
  await expect(page.getByText(/Some imagery tiles are unavailable/)).toBeVisible();
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await expect(page.getByRole("button", { name: "Reset map view", exact: true })).toBeEnabled();
  await expect(page.getByText(/^Map unavailable:/)).toHaveCount(0);
});

test("World map uses actual NASA tiles, reviewed geography and saved operator areas", async ({ page, context }) => {
  test.setTimeout(60000);
  const fixture = loadCapturedIntelGlobeFixture();
  const failures: string[] = [];
  page.on("pageerror", error => failures.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/osint/scene/intel**", route => route.fulfill({ json: fixture.scene_payload }));
  await page.route("**/api/intel/meta**", route => route.fulfill({ json: fixture.intel_meta_payload }));
  const tile = page.waitForResponse(response => response.url().startsWith("https://gibs.earthdata.nasa.gov/") && response.ok(), { timeout: 30000 });
  await page.goto("/osint?tab=intel");
  await page.getByTestId("osint-open-globe").click();
  await page.getByTestId("globe-scene-intel").click();
  await tile;
  await expect(page.getByTestId("world-map-canvas").locator("canvas")).toBeVisible();
  await expect(page.getByText("Loading world view...", { exact: true })).toHaveCount(0);
  const center = page.getByLabel("Map center coordinates", { exact: true });
  await expect(center).toHaveText("17.500°, 7.200°");
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await page.getByLabel("Research-area passphrase", { exact: true }).fill("isolated-map-ui-passphrase");
  await page.getByLabel("Repeat research-area passphrase", { exact: true }).fill("isolated-map-ui-passphrase");
  await page.getByRole("button", { name: "Create encrypted area storage", exact: true }).click();
  await page.getByLabel("Find country", { exact: true }).fill("France");
  await page.getByRole("button", { name: "France", exact: true }).click();
  await page.getByLabel("Map projection", { exact: true }).selectOption("mercator");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await page.getByLabel("Research area name", { exact: true }).fill("Browser-verified viewport");
  await page.getByRole("button", { name: "Save current map area", exact: true }).click();
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toBeVisible();
  const ciphertext = await page.evaluate(key => localStorage.getItem(key), AREA_STORAGE_KEY);
  expect(ciphertext).not.toContain("Browser-verified viewport");
  expect(ciphertext).not.toContain("bounds");
  await page.getByRole("button", { name: "Lock research areas", exact: true }).click();
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toHaveCount(0);
  await page.getByLabel("Research-area passphrase", { exact: true }).fill("incorrect-passphrase");
  await page.getByRole("button", { name: "Unlock research areas", exact: true }).click();
  await expect(page.getByText(/Could not unlock research areas/)).toBeVisible();
  expect(await page.evaluate(key => localStorage.getItem(key), AREA_STORAGE_KEY)).toBe(ciphertext);
  await page.getByLabel("Research-area passphrase", { exact: true }).fill("isolated-map-ui-passphrase");
  await page.getByRole("button", { name: "Unlock research areas", exact: true }).click();
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toBeVisible();
  const secondTab = await context.newPage();
  await secondTab.goto("/");
  await secondTab.evaluate(async () => {
    const { openAreaVault, saveAreaVault } = await import("/src/lib/researchAreaVault.ts");
    const session = await openAreaVault("isolated-map-ui-passphrase", false, () => true);
    await saveAreaVault(session, session.areas, () => true);
  });
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toHaveCount(0);
  await expect(page.getByText(/Research areas changed in another tab/)).toBeVisible();
  await secondTab.close();
  await page.getByRole("button", { name: "Close world view", exact: true }).click();
  await page.getByTestId("osint-open-globe").click();
  await page.getByTestId("globe-scene-intel").click();
  await expect(center).toHaveText("17.500°, 7.200°");
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await expect(page.getByRole("button", { name: "Unlock research areas", exact: true })).toBeVisible();
  await page.getByLabel("Research-area passphrase", { exact: true }).fill("isolated-map-ui-passphrase");
  await page.getByRole("button", { name: "Unlock research areas", exact: true }).click();
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toBeVisible();
  await expect(page.getByText(/operator-defined viewport bounds/)).toBeVisible();
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await page.screenshot({ path: "test-results/world-map-desktop.jpg", quality: 65 });
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await page.getByLabel("Map projection", { exact: true }).selectOption("mercator");
  await page.getByLabel("Show satellite or street imagery").uncheck();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/world-map-mobile.jpg", quality: 65 });
  await page.getByRole("button", { name: "Remove Browser-verified viewport", exact: true }).click();
  await expect(page.getByRole("button", { name: "Browser-verified viewport", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Reset map view", exact: true }).click();
  await expect(center).toHaveText("17.500°, 7.200°");
  await page.getByLabel("Map projection", { exact: true }).selectOption("globe");
  await page.getByRole("button", { name: "Map tools", exact: true }).click();
  await page.getByTestId("globe-controls-toggle").click();
  await page.getByTestId("globe-preset-overview").click();
  const canvas = page.getByTestId("world-map-canvas").locator("canvas");
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await expect(center).not.toHaveText("17.500°, 7.200°");
  await page.getByTestId("globe-preset-overview").click();
  await expect(center).toHaveText("17.500°, 7.200°");
  await page.getByTestId("globe-controls-toggle").click();
  await page.getByTestId("globe-browse-toggle").click();
  await page.locator("#globe-browse-panel button").first().click();
  await expect(page.getByTestId("globe-inspector")).not.toContainText("Select an object on the globe");
  await page.getByRole("button", { name: "Collapse context panel", exact: true }).click();
  await page.screenshot({ path: "test-results/world-map-mobile-browse.jpg", quality: 65 });
  expect(failures).toEqual([]);
});

test("encrypted backup download recovers the real isolated canonical database", async ({ page }) => {
  await page.goto("/system");
  await page.getByRole("button", { name: "Download encrypted backup", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Export encrypted database backup" });
  await dialog.getByLabel("Backup passphrase", { exact: true }).fill("isolated-browser-recovery-passphrase");
  await dialog.getByLabel("Repeat backup passphrase", { exact: true }).fill("isolated-browser-recovery-passphrase");
  const downloadEvent = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Confirm and download backup", exact: true }).click();
  const download = await downloadEvent;
  const directory = fs.mkdtempSync(path.resolve("test-results/recovery-"));
  const archive = path.join(directory, "snapshot.clearbackup");
  const restored = path.join(directory, "verified.db");
  await download.saveAs(archive);
  const result = JSON.parse(execFileSync("python", ["-c", "import json,sys,sqlite3; from pathlib import Path; from utils.recovery import restore_to_new_file; from contextlib import closing; manifest=restore_to_new_file(Path(sys.argv[1]).read_bytes(), sys.stdin.read(), Path(sys.argv[2])); db=sqlite3.connect(sys.argv[2]); count=db.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]; db.close(); print(json.dumps({'scope': manifest['scope'], 'tables': count}))", archive, restored], { cwd: path.resolve(".."), input: "isolated-browser-recovery-passphrase", encoding: "utf8" }));
  expect(result.scope).toBe("canonical-sqlite-database");
  expect(result.tables).toBeGreaterThan(0);
  await expect(page.getByRole("status").filter({ hasText: "Encrypted backup download started" })).toBeVisible();
});

function isListening(port: number): Promise<boolean> {
  return new Promise(resolve => { const socket = net.createConnection({ host: "127.0.0.1", port }); socket.setTimeout(500); socket.once("connect", () => { socket.destroy(); resolve(true); }); socket.once("error", () => resolve(false)); socket.once("timeout", () => { socket.destroy(); resolve(false); }); });
}

test("close app confirms and stops both real isolated servers", async ({ page }) => {
  const runtimeRoot = path.resolve("../test_runtime");
  const runtimes = fs.readdirSync(runtimeRoot).filter(name => name.startsWith(`advisory-browser-${process.env.CLEAR_ACCEPTANCE_RUN_ID}-`));
  expect(runtimes).toHaveLength(1);
  const controlDir = path.join(runtimeRoot, runtimes[0], "data/runtime");
  const controlName = fs.readdirSync(controlDir).find(name => name.startsWith("stack-") && name.endsWith(".json"))!;
  const controlPath = path.join(controlDir, controlName);
  const ownership = JSON.parse(fs.readFileSync(controlPath, "utf8"));
  await page.goto("/");
  await page.getByRole("button", { name: "Close app", exact: true }).click();
  await page.getByRole("button", { name: "Keep working" }).click();
  await expect(page.getByRole("heading", { name: "Your work, in focus." })).toBeVisible();
  await page.getByRole("button", { name: "Close app", exact: true }).click();
  const shutdownStarted = Date.now();
  await page.getByRole("button", { name: "Close Clear safely" }).click();
  await expect(page.getByRole("heading", { name: "Clear is shutting down." })).toBeVisible();
  await expect.poll(async () => [await isListening(18080), await isListening(15173)], { timeout: 25000 }).toEqual([false, false]);
  await expect.poll(() => JSON.parse(execFileSync("python", ["-c", "import json,sys,psutil; records=json.loads(sys.argv[1]); identities=[identity for record in records.values() for identity in [record]+record.get('children',[])]; running={p.pid:p.create_time() for p in psutil.process_iter()}; print(json.dumps([i['pid'] for i in identities if running.get(i['pid'])==i['created']]))", JSON.stringify(ownership.processes)], { encoding: "utf8" })), { timeout: 10000 }).toEqual([]);
  expect(JSON.parse(fs.readFileSync(controlPath, "utf8")).shutdown_result).toBe("stopped");
  console.log(`Idle stack shutdown verified in ${Date.now() - shutdownStarted} ms`);
});
