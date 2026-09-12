import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "..");
const ROOT_ENV_PATH = path.join(ROOT_DIR, ".env");

function loadRootEnvValue(...names: string[]): string {
  for (const name of names) {
    const fromProcess = process.env[name];
    if (fromProcess) return fromProcess;
  }
  if (!fs.existsSync(ROOT_ENV_PATH)) return "";
  const content = fs.readFileSync(ROOT_ENV_PATH, "utf-8");
  for (const name of names) {
    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const [key, ...rest] = trimmed.split("=");
      if (key !== name) continue;
      return rest.join("=").trim().replace(/^['"]|['"]$/g, "");
    }
  }
  return "";
}

const API_KEY = loadRootEnvValue("LOTBOOK_WEB_API_KEY", "CLEAR_WEB_API_KEY");
const API_BASE = "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./tests",
  // Mutating acceptance tests require their disposable launcher configuration.
  testIgnore: ["**/advisory.spec.ts"],
  timeout: 60000,
  expect: {
    timeout: 10000
  },
  webServer: [
    {
      command: "python -m uvicorn web_api.app:app --host 127.0.0.1 --port 8000 --app-dir ..",
      url: "http://127.0.0.1:8000/openapi.json",
      reuseExistingServer: true,
      cwd: ROOT_DIR,
      env: {
        ...process.env,
        LOTBOOK_WEB_API_KEY: API_KEY
      }
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      env: {
        ...process.env,
        VITE_API_BASE: API_BASE,
        VITE_API_KEY: API_KEY
      }
    }
  ],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure"
  },
  reporter: process.env.CI
    ? [["junit", { outputFile: "test-results/junit.xml" }]]
    : "list",
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
