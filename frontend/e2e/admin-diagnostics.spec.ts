import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", role: "admin", must_change_password: false }

test("admin diagnostics renders readable storage sizes", async ({ page }) => {
  let requests = 0
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/diagnostics", route => {
    requests += 1
    return route.fulfill({ json: {
    application: { version: "1.5.1", environment: "development" },
    database: { backend: "sqlite", reachable: true, size_bytes: 1_610_612_736 },
    storage: { data: { path: "/data", readable: true, writable: true, total_bytes: 2_199_023_255_552, free_bytes: 1_099_511_627_776 }, backup: { path: "/backups", readable: true, writable: false } },
    archive_backend: { command: "7z", available: true }, scanner: { max_concurrent_scans: 1, running: 0, pending: 0 },
    scheduler: { thread_alive: true, last_check_at: null, last_success_at: null, last_error_at: null, last_error: null },
    catalogue: { models_total: 1, models_available: 1, models_incomplete: 0, models_error: 0, models_missing: 0, archives_total: 1, archives_error: 0 },
  } })
  })

  await page.goto("/admin/diagnostics")
  await expect(page.getByRole("heading", { name: "Diagnostics", level: 1 })).toBeVisible()
  await expect(page.getByText("2 TB")).toBeVisible()
  await expect(page.getByText("1.5 GB")).toBeVisible()
  await expect(page.getByText("Readable and writable")).toBeVisible()
  await expect(page.getByText("Readable, read-only")).toBeVisible()
  await expect(page.getByText("Unavailable").first()).toBeVisible()
  await expect(page.getByText("Lightweight status checks only")).toBeVisible()
  await page.getByRole("button", { name: "Refresh" }).click()
  await expect.poll(() => requests).toBe(2)
})

test("diagnostics safely renders unavailable capacity", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/diagnostics", route => route.fulfill({ json: {
    application: { version: "1.5.1", environment: "test" }, database: { backend: "sqlite", reachable: true },
    storage: { cache: { path: "/cache", readable: false, writable: false } }, archive_backend: { command: "7z", available: true },
    scanner: { max_concurrent_scans: 1, running: 0, pending: 0 }, scheduler: { thread_alive: true, last_check_at: null, last_success_at: null, last_error_at: null, last_error: null }, catalogue: {},
  } }))
  await page.goto("/admin/diagnostics")
  await expect(page.getByText("Unavailable").first()).toBeVisible()
})
