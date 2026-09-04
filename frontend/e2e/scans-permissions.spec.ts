import { expect, test } from "@playwright/test"

function user(permissions: string[], sourceIds = [1]) {
  return { id: 1, username: "Operator", email: null, email_verified: false, role: "user", is_active: true, must_change_password: false, permissions, source_access: { all_sources: false, source_ids: sourceIds } }
}

async function mockScans(page: import("@playwright/test").Page, permissions: string[]) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user(permissions) }))
  await page.route("**/api/admin/scans/library-sources", route => route.fulfill({ json: [{ id: 1, name: "Source A" }] }))
}

test("view-only operator sees scoped scan history without start controls", async ({ page }) => {
  await mockScans(page, ["scans.view"])
  await page.route("**/api/admin/library-sources/1/scans", route => route.fulfill({ json: [{ id: 4, library_source_id: 1, status: "completed", mode: "smart", created_at: "2026-01-01", models_found: 3, models_added: 1, models_updated: 0, models_missing: 0, error_message: null }] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [] }))
  await page.goto("/admin/scans")
  await expect(page.getByRole("heading", { name: "Source A" })).toBeVisible()
  await expect(page.getByText("1 recent scans")).toBeVisible()
  await expect(page.getByRole("button", { name: "Start scan" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Library sources" })).toHaveCount(0)
})

test("start-only operator starts a smart scan without history requests", async ({ page }) => {
  let historyRequested = false
  let queueRequested = false
  let started = false
  await mockScans(page, ["scans.start"])
  await page.route("**/api/admin/library-sources/1/scans", route => { historyRequested = true; return route.fulfill({ json: [] }) })
  await page.route("**/api/admin/scans/queue", route => { queueRequested = true; return route.fulfill({ json: [] }) })
  await page.route("**/api/admin/library-sources/1/scan", async route => { started = route.request().postDataJSON().mode === "smart"; await route.fulfill({ json: {} }) })
  await page.goto("/admin/scans")
  await expect(page.getByRole("heading", { name: "Source A" })).toBeVisible()
  await page.getByRole("button", { name: "Start smart scan" }).click()
  await expect.poll(() => started).toBe(true)
  expect(historyRequested).toBe(false)
  expect(queueRequested).toBe(false)
})

test("show all expands only the selected source history", async ({ page }) => {
  await mockScans(page, ["scans.view"])
  await page.route("**/api/admin/scans/library-sources", route => route.fulfill({ json: [{ id: 1, name: "Source A" }, { id: 2, name: "Source B" }] }))
  await page.route("**/api/admin/library-sources/*/scans", route => {
    const sourceId = Number(route.request().url().match(/library-sources\/(\d+)/)?.[1])
    const scans = Array.from({ length: 6 }, (_, index) => ({ id: sourceId * 10 + index, library_source_id: sourceId, status: "completed_with_errors", mode: "reconcile_images", created_at: "2026-01-01", models_found: index, models_added: 0, models_updated: 0, models_missing: 0, error_message: null }))
    return route.fulfill({ json: scans })
  })
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [] }))
  await page.goto("/admin/scans")
  await expect(page.getByText("Completed with issues")).toHaveCount(10)
  await expect(page.getByText("Show all 6 scans")).toHaveCount(2)
  await page.getByText("Show all 6 scans").first().click()
  await expect(page.getByText("Completed with issues")).toHaveCount(11)
  await expect(page.getByText("Show fewer scans")).toHaveCount(1)
  await expect(page.getByText("Show all 6 scans")).toHaveCount(1)
  await expect(page.getByText("Reconcile images")).toHaveCount(11)
})

test("users without scan permissions cannot open scans", async ({ page }) => {
  await mockScans(page, ["catalogue.view"])
  await page.route("**/api/models/filters**", route => route.fulfill({ json: { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] } }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 48 } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.goto("/admin/scans")
  await expect(page).toHaveURL(/\/(?:\?.*)?$/)
  await expect(page.getByRole("link", { name: "Scans" })).toHaveCount(0)
})
