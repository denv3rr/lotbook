import { defineConfig, devices } from "@playwright/test";
import { randomUUID } from "node:crypto";

process.env.CLEAR_ACCEPTANCE_RUN_ID ||= randomUUID();

export default defineConfig({
  testDir: "./tests", testMatch: "advisory.spec.ts", timeout: 120000,
  workers: 1, fullyParallel: false, retries: 0,
  use: { baseURL: "http://127.0.0.1:15173", trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: { command: "python ../scripts/run_browser_stack.py", url: "http://127.0.0.1:15173", reuseExistingServer: false, timeout: 90000 },
});
