import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 15_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    timeout: 30_000,
    reuseExistingServer: !process.env.CI,
  },
})
