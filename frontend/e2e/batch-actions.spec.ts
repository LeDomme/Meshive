import { expect, test } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const filters = { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }
const models = [1, 2].map(id => ({ id, name: `Model ${id}`, variant: null, creator: null, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }))

test("batch rescan processes selected models in deterministic order", async ({ page }) => {
  const rescanned: number[] = []
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: models, total: 2, page: 1, page_size: 48 } }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route(/\/api\/admin\/models\/(\d+)\/rescan/, async route => { rescanned.push(Number(route.request().url().match(/models\/(\d+)/)?.[1])); await route.fulfill({ json: {} }) })
  page.on("dialog", dialog => dialog.accept())
  await page.goto("/")
  await page.getByRole("button", { name: "Select models" }).click()
  await page.getByRole("checkbox", { name: /Model 1/ }).click()
  await page.getByRole("checkbox", { name: /Model 2/ }).click()
  await page.getByRole("button", { name: "Rescan selected" }).click()
  await expect.poll(() => rescanned).toEqual([1, 2])
  await expect(page.getByText("2 selected")).toBeVisible()
})

test("batch picture reset uses the image endpoint and never queues a rescan", async ({ page }) => {
  const reset: number[] = []
  let rescanCalled = false
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: models, total: 2, page: 1, page_size: 48 } }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route(/\/api\/admin\/models\/(\d+)\/images/, async route => { reset.push(Number(route.request().url().match(/models\/(\d+)/)?.[1])); expect(route.request().method()).toBe("DELETE"); await route.fulfill({ json: { deleted: 0 } }) })
  await page.route("**/api/admin/models/*/rescan", route => { rescanCalled = true; return route.fulfill({ json: {} }) })
  page.on("dialog", dialog => dialog.accept())
  await page.goto("/")
  await page.getByRole("button", { name: "Select models" }).click()
  await page.getByRole("checkbox", { name: /Model 1/ }).click()
  await page.getByRole("button", { name: "Reset selected pictures" }).click()
  await expect.poll(() => reset).toEqual([1])
  expect(rescanCalled).toBe(false)
})
