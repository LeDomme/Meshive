import { expect, test, type Page } from "@playwright/test"

const user = { id: 1, username: "Curator", email: null, email_verified: false, role: "curator", is_active: true, must_change_password: false, permissions: ["catalogue.view", "models.rescan", "models.rebuild_images", "models.reset_images"], source_access: { all_sources: true, source_ids: [] } }
const filters = { models: [], creators: [{ value: "Ada", count: 1 }], franchises: [], series: [], collections: [], sources: [{ id: 1, name: "Library", count: 1 }], statuses: [], tags: [] }
const model = { id: 1, name: "Selectable model", variant: null, creator: "Ada", franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }

async function documentY(page: Page, selector: string) {
  return page.locator(selector).evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
}

async function filterControlsBottom(page: Page) {
  return page.locator(".catalogue-filters").evaluate((row) => Math.max(
    ...[...row.querySelectorAll<HTMLElement>(".searchable-filter-trigger, .secondary-button")]
      .map((control) => control.getBoundingClientRect().bottom + window.scrollY),
  ))
}

test("catalogue controls contain selection status and bulk actions", async ({ page }) => {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [model], total: 1, page: 1, page_size: 48 } }))
  await page.goto("/?creator=Ada")

  const controls = page.locator(".catalogue-controls")
  const grid = page.locator(".model-grid")
  const filterRow = page.locator(".catalogue-filters")
  const footer = page.locator(".catalogue-meta")
  await expect(controls).toContainText("1 model")
  await expect(controls.getByRole("button", { name: "Select models" })).toBeVisible()
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toHaveCount(0)

  const controlsBefore = await controls.boundingBox()
  const gridBefore = await grid.boundingBox()
  const gridDocumentY = await documentY(page, ".model-grid")
  const filtersBefore = await filterRow.boundingBox()
  const footerBefore = await footer.boundingBox()
  const dividerDocumentY = await documentY(page, ".catalogue-meta")
  const filterBottomDocumentY = await filterControlsBottom(page)
  expect(gridBefore?.y).toBeGreaterThan((controlsBefore?.y ?? 0) + (controlsBefore?.height ?? 0) + 15)
  expect(footerBefore?.y).toBeGreaterThanOrEqual((filtersBefore?.y ?? 0) + (filtersBefore?.height ?? 0))
  expect(dividerDocumentY).toBeGreaterThanOrEqual(filterBottomDocumentY + 10)
  await expect(footer).toHaveCSS("border-top-width", "1px")
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
  const selectionGridY = await documentY(page, ".model-grid")
  const selectionFilters = await filterRow.boundingBox()
  const selectionFooter = await footer.boundingBox()
  const selectionDividerDocumentY = await documentY(page, ".catalogue-meta")
  expect(selectionControls?.height).toBe(controlsBefore?.height)
  expect(selectionGridY).toBe(gridDocumentY)
  expect(selectionFilters?.y).toBe(filtersBefore?.y)
  expect(selectionDividerDocumentY).toBe(dividerDocumentY)
  expect(selectionFooter?.y).toBeGreaterThanOrEqual((selectionFilters?.y ?? 0) + (selectionFilters?.height ?? 0))
  await expect(controls.locator(".catalogue-selection")).toBeVisible()
  await expect(controls).toContainText("1 model")
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toBeVisible()
  await expect(controls.getByRole("button", { name: "Done selecting" })).toBeVisible()
  await page.locator(".model-card").click()
  await expect(controls).toContainText("1 selected")
  await controls.getByRole("button", { name: "Clear selection" }).click()
  await expect(controls.getByText("1 selected", { exact: true })).toHaveCount(0)
  await controls.getByRole("button", { name: "Done selecting" }).click()
  const controlsAfterDone = await controls.boundingBox()
  const gridAfterDoneY = await documentY(page, ".model-grid")
  await expect(controls.getByRole("button", { name: "Rescan selected" })).toHaveCount(0)
  await expect(controls.locator(".catalogue-selection")).toHaveCount(0)
  expect(controlsAfterDone?.height).toBe(controlsBefore?.height)
  expect(gridAfterDoneY).toBe(gridDocumentY)
  await expect(page).toHaveURL(/\?creator=Ada&sort=name_asc$/)
})
