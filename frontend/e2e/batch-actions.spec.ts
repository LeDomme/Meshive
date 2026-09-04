import { expect, test } from "@playwright/test"

const filters = { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [{ value: "missing", count: 1 }], tags: [] }
const models = [1, 2].map(id => ({ id, name: `Model ${id}`, variant: null, creator: null, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }))
const missingModel = { ...models[0], id: 3, name: "Missing model", status: "missing" }

function userWith(permissions: string[]) {
  return { id: 1, username: "User", email: null, email_verified: false, role: "user", is_active: true, must_change_password: false, permissions, source_access: { all_sources: true, source_ids: [] } }
}

async function mockCatalogue(page: import("@playwright/test").Page, permissions: string[], items = models) {
  await page.route("**/api/auth/me", route => route.fulfill({ json: userWith(permissions) }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items, total: items.length, page: 1, page_size: 48 } }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
}

test("catalogue-only users see no maintenance or batch controls", async ({ page }) => {
  await mockCatalogue(page, ["catalogue.view"], [missingModel])
  await page.goto("/")
  await expect(page.locator("[data-filter-key='status']")).toHaveCount(0)
  await expect(page.locator(".model-status")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Select models" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: /Delete all missing/ })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Delete from database" })).toHaveCount(0)
})

test("maintenance permission reveals status information without batch actions", async ({ page }) => {
  await mockCatalogue(page, ["catalogue.view", "catalogue.view_maintenance"], [missingModel])
  await page.goto("/")
  await expect(page.locator("[data-filter-key='status']")).toBeVisible()
  await expect(page.locator(".model-status")).toHaveText("missing")
  await expect(page.getByRole("button", { name: "Select models" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Delete from database" })).toHaveCount(0)
})

test("batch rescan processes selected models in deterministic order", async ({ page }) => {
  const rescanned: number[] = []
  await mockCatalogue(page, ["catalogue.view", "models.rescan"])
  await page.route(/\/api\/admin\/models\/(\d+)\/rescan/, async route => { rescanned.push(Number(route.request().url().match(/models\/(\d+)/)?.[1])); await route.fulfill({ json: {} }) })
  page.on("dialog", dialog => dialog.accept())
  await page.goto("/")
  await page.getByRole("button", { name: "Select models" }).click()
  await page.getByRole("checkbox", { name: /Model 1/ }).click()
  await page.getByRole("checkbox", { name: /Model 2/ }).click()
  await page.getByRole("button", { name: "Rescan selected" }).click()
  await expect.poll(() => rescanned).toEqual([1, 2])
  await expect(page.getByRole("button", { name: "Rebuild selected images" })).toHaveCount(0)
})

test("batch rebuild is independently available and does not rescan", async ({ page }) => {
  const rebuilt: number[] = []
  let rescanCalled = false
  await mockCatalogue(page, ["catalogue.view", "models.rebuild_images"])
  await page.route(/\/api\/admin\/models\/(\d+)\/rebuild-images/, async route => { rebuilt.push(Number(route.request().url().match(/models\/(\d+)/)?.[1])); await route.fulfill({ json: {} }) })
  await page.route("**/api/admin/models/*/rescan", route => { rescanCalled = true; return route.fulfill({ json: {} }) })
  page.on("dialog", dialog => dialog.accept())
  await page.goto("/")
  await page.getByRole("button", { name: "Select models" }).click()
  await page.getByRole("checkbox", { name: /Model 1/ }).click()
  await page.getByRole("button", { name: "Rebuild selected images" }).click()
  await expect.poll(() => rebuilt).toEqual([1])
  expect(rescanCalled).toBe(false)
  await expect(page.getByRole("button", { name: "Rescan selected" })).toHaveCount(0)
})

test("combined batch permissions expose both permitted actions", async ({ page }) => {
  await mockCatalogue(page, ["catalogue.view", "models.rescan", "models.rebuild_images"])
  await page.goto("/")
  await page.getByRole("button", { name: "Select models" }).click()
  await page.getByRole("checkbox", { name: /Model 1/ }).click()
  await expect(page.getByRole("button", { name: "Rescan selected" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Rebuild selected images" })).toBeVisible()
})

test("missing-model deletion requires maintenance and delete permission", async ({ page }) => {
  let deleted = false
  await mockCatalogue(page, ["catalogue.view", "catalogue.view_maintenance", "models.delete_missing"], [missingModel])
  await page.route("**/api/admin/models/missing", async route => { deleted = true; await route.fulfill({ json: { deleted: 1 } }) })
  page.on("dialog", dialog => dialog.accept())
  await page.goto("/")
  await expect(page.getByRole("button", { name: "Delete from database" })).toBeVisible()
  await expect(page.getByRole("button", { name: /Delete all missing/ })).toBeVisible()
  await expect(page.getByRole("button", { name: "Select models" })).toHaveCount(0)
  await page.getByRole("button", { name: /Delete all missing/ }).click()
  await expect.poll(() => deleted).toBe(true)
})
