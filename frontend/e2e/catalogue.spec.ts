import { expect, test, type Page } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false, permissions: ["catalogue.view"], source_access: { all_sources: true, source_ids: [] } }
const filters = { models: [], creators: [{ value: "Ada", count: 1 }], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }
const model = { id: 7, name: "Ada Model", variant: null, creator: "Ada", franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }

async function mockCatalogue(page: Page, requests: string[]) {
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/saved-views", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => { requests.push(route.request().url()); return route.fulfill({ json: { items: [model], total: 1, page: 1, page_size: 48 } }) })
}

test("saved views restore catalogue filters, source scope, and sorting", async ({ page }) => {
  const requests: string[] = []
  let savedView: Record<string, unknown> | undefined
  await mockCatalogue(page, requests)
  await page.unroute("**/api/saved-views")
  await page.route("**/api/saved-views", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: savedView ? [savedView] : [] })
    const body = route.request().postDataJSON() as { name: string; state: Record<string, string> }
    savedView = { id: 1, name: body.name, state: body.state, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:00Z" }
    return route.fulfill({ status: 201, json: savedView })
  })
  await page.goto("/?creator=Ada&source_id=1&sort=creator_desc")
  const savedViewSelect = page.locator("#saved-view-select")
  await expect(savedViewSelect).toHaveValue("")
  await expect(savedViewSelect.locator("option")).toHaveCount(1)
  await expect(savedViewSelect.locator("option").first()).toHaveText("Saved views")
  await expect(page.getByRole("button", { name: "Rename" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Delete" })).toHaveCount(0)
  await expect(page.locator(".catalogue-filters #saved-view-select")).toHaveCount(0)
  await expect(page.locator(".catalogue-meta #saved-view-select")).toBeVisible()
  page.once("dialog", dialog => dialog.accept("Ada collection"))
  await page.getByRole("button", { name: "Save view" }).click()
  await expect(savedViewSelect).toHaveValue("1")
  await expect(savedViewSelect.locator("option:checked")).toHaveText("Ada collection")
  await expect(page.getByRole("button", { name: "Rename" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Delete" })).toBeVisible()
  await page.getByRole("button", { name: "Clear" }).click()
  await expect(savedViewSelect).toHaveValue("")
  await page.selectOption("#saved-view-select", "1")
  await expect(savedViewSelect.locator("option:checked")).toHaveText("Ada collection")
  await expect.poll(() => requests.some((url) =>
    url.includes("creator=Ada") && url.includes("source_id=1") && url.includes("sort=creator_desc"),
  )).toBe(true)
})

test("catalogue creator filter and sort update the request state", async ({ page }) => {
  const requests: string[] = []
  await mockCatalogue(page, requests)
  await page.goto("/")
  await page.getByRole("button", { name: "Creator" }).click()
  await page.getByRole("option", { name: "Ada" }).click()
  await expect.poll(() => requests.some((url) => url.includes("creator=Ada"))).toBe(true)
  await page.getByRole("button", { name: "Sort models" }).click()
  await page.getByRole("option", { name: "Creator: Z–A" }).click()
  await expect.poll(() => requests.some((url) => url.includes("creator=Ada") && url.includes("sort=creator_desc"))).toBe(true)
  await expect(page.getByRole("heading", { name: "Ada Model" })).toBeVisible()
})

test("clearing catalogue filters removes stale request parameters", async ({ page }) => {
  const requests: string[] = []
  await mockCatalogue(page, requests)
  await page.goto("/?creator=Ada&sort=creator_desc")
  await page.getByRole("button", { name: "Clear" }).click()
  await expect.poll(() => requests.some((url) => !url.includes("creator=") && url.includes("sort=name_asc"))).toBe(true)
  await expect(page).toHaveURL(/\?sort=name_asc$/)
})

test("catalogue pagination returns to the top after loading a new page", async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as Window & { catalogueScrollCalls?: ScrollToOptions[] }).catalogueScrollCalls = []
    window.scrollTo = (options?: ScrollToOptions | number) => {
      if (typeof options === "object") {
        ;(window as Window & { catalogueScrollCalls: ScrollToOptions[] }).catalogueScrollCalls.push(options)
      }
    }
  })
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => {
    const requestedPage = new URL(route.request().url()).searchParams.get("page")
    const pageNumber = Number(requestedPage || "1")
    return route.fulfill({
      json: {
        items: [{ ...model, id: pageNumber, name: `Page ${pageNumber} model` }],
        total: 96,
        page: pageNumber,
        page_size: 48,
      },
    })
  })

  await page.goto("/")
  await page.getByRole("button", { name: "Go to next page" }).click()

  await expect(page.getByRole("heading", { name: "Page 2 model" })).toBeVisible()
  await expect.poll(() => page.evaluate(() =>
    (window as Window & { catalogueScrollCalls: ScrollToOptions[] }).catalogueScrollCalls,
  )).toEqual([{ top: 0, behavior: "smooth" }])
})
