import { expect, test, type Page } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const filters = { models: [], creators: [{ value: "Ada", count: 1 }], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }
const model = { id: 7, name: "Ada Model", variant: null, creator: "Ada", franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }

async function mockCatalogue(page: Page, requests: string[]) {
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => { requests.push(route.request().url()); return route.fulfill({ json: { items: [model], total: 1, page: 1, page_size: 48 } }) })
}

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
