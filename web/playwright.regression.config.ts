import { defineConfig } from "@playwright/test";
import advisory from "./playwright.advisory.config";

export default defineConfig({
  ...advisory,
  testMatch: ["assistant.spec.ts", "auth.spec.ts", "system.spec.ts", "smoke.spec.ts"],
  grep: /advisory landing|assistant|auth error banner|system maintenance/,
});
