import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Curator", email: null, email_verified: false, role: "curator", is_active: true, must_change_password: false, permissions: ["catalogue.view", "models.rescan", "models.rebuild_images", "models.reset_images"], source_access: { all_sources: true, source_ids: [] } }
const filters = { models: [], creators: [{ value: "Ada", count: 1 }], franchises: [], series: [], collections: [], sources: [{ id: 1, name: "Library", count: 1 }], statuses: [], tags: [] }
const model = { id: 1, name: "Selectable model", variant: null, creator: "Ada", franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }

test("catalogue controls contain selection status and bulk actions", async ({ page }) => {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [model], total: 1, page: 1, page_size: 48 } }))
  await page.goto("/?creator=Ada")

  const controls = page.locator(".catalogue-controls")
  const grid = page.locator(".model-grid")
  await expect(controls).toContainText("1 model")
  await expect(controls.getByRole("button", { name: "Select models" })).toBeVisible()
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toHaveCount(0)

  const controlsBefore = await controls.boundingBox()
  const gridBefore = await grid.boundingBox()
  expect(gridBefore?.y).toBeGreaterThan((controlsBefore?.y ?? 0) + (controlsBefore?.height ?? 0) + 15)
  await controls.getByRole("button", { name: "Library source" }).click()
  const dropdown = page.locator(".searchable-filter-panel")
  await expect(dropdown).toBeVisible()
  const controlsAfter = await controls.boundingBox()
  const dropdownBox = await dropdown.boundingBox()
  expect(controlsAfter?.height).toBe(controlsBefore?.height)
  expect(controlsAfter?.y).toBe(controlsBefore?.y)
  expect(dropdownBox?.y).toBeGreaterThan(controlsAfter?.y ?? 0)
  expect(dropdownBox?.y).toBeLessThan(gridBefore?.y ?? 0)
  await page.keyboard.press("Escape")

  await controls.getByRole("button", { name: "Select models" }).click()
  const selectionControls = await controls.boundingBox()
  expect(selectionControls?.height).toBeGreaterThan(controlsBefore?.height ?? 0)
  await expect(controls.locator(".catalogue-selection")).toBeVisible()
  await expect(controls).toContainText("1 model")
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toBeVisible()
  await expect(controls.getByRole("button", { name: "Done selecting" })).toBeVisible()
  await page.locator(".model-card").click()
  await expect(controls).toContainText("1 selected")
  await controls.getByRole("button", { name: "Clear selection" }).click()
  await expect(controls.getByText("1 selected", { exact: true })).toHaveCount(0)
  await controls.getByRole("button", { name: "Done selecting" }).click()
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toHaveCount(0)
  await expect(controls.locator(".catalogue-selection")).toHaveCount(0)
  await expect(page).toHaveURL(/\?creator=Ada&sort=name_asc$/)
})
