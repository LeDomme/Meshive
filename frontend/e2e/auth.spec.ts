import { expect, test } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false, permissions: ["catalogue.view", "diagnostics.view"], source_access: { all_sources: true, source_ids: [] } }
const user = { ...admin, id: 2, username: "User", role: "user", permissions: [] }
const emptyFilters = { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }

test("login submits credentials and opens the catalogue", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: null }))
  await page.route("**/api/auth/password-recovery/status", route => route.fulfill({ json: { enabled: false } }))
  await page.route("**/api/auth/login", async route => {
    expect(route.request().postDataJSON()).toEqual({ username: "admin", password: "secret" })
    await route.fulfill({ json: admin })
  })
  await page.route("**/api/models/filters**", route => route.fulfill({ json: emptyFilters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 24 } }))

  await page.goto("/login")
  await page.getByLabel("Username").fill("admin")
  await page.getByLabel("Password").fill("secret")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/(?:\?.*)?$/)
})

test("regular users are redirected away from administration", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: emptyFilters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 24 } }))

  await page.goto("/admin/diagnostics")
  await expect(page).toHaveURL(/\/access-denied$/)
  await expect(page.getByRole("link", { name: "Diagnostics" })).toHaveCount(0)
})

test("administrators can open diagnostics from administration navigation", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/admin/diagnostics", route => route.fulfill({ json: {
    application: { version: "1.5.2", environment: "test" }, database: { backend: "sqlite", reachable: true }, storage: {},
    archive_backend: { command: "7z", available: true }, scanner: { max_concurrent_scans: 1, running: 0, pending: 0 },
    scheduler: { thread_alive: true, last_check_at: null, last_success_at: null, last_error_at: null, last_error: null }, catalogue: {},
  } }))

  await page.goto("/admin/diagnostics")
  await expect(page.getByRole("link", { name: "Diagnostics" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Diagnostics", level: 1 })).toBeVisible()
})
