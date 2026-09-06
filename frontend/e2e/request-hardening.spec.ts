import { expect, test, type Page } from "@playwright/test"

const admin = {
  id: 1,
  username: "Admin",
  email: null,
  email_verified: false,
  role: "admin",
  is_active: true,
  must_change_password: false,
  permissions: ["catalogue.view", "favorites.manage"],
  source_access: { all_sources: true, source_ids: [] },
}

const filters = (creator: string) => ({
  models: [],
  creators: [{ value: creator, count: 1 }],
  franchises: [],
  series: [],
  collections: [],
  sources: [],
  statuses: [],
  tags: [],
})

const model = (id: number, name: string) => ({
  id,
  name,
  variant: null,
  creator: null,
  franchise: null,
  series: null,
  collection: null,
  status: "available",
  source_id: 1,
  source_name: "Library",
  archive_format: "7z",
  archive_size_bytes: 1,
  archive_count: 1,
  thumbnail_url: null,
  tags: [],
})

const detail = (id: number) => ({
  ...model(id, `Model ${id}`),
  creator_links: [],
  relative_path: `Model ${id}`,
  images: [],
  archives: [],
  archive_bundle_download_url: null,
  recent_scan_issues: [],
  archive_statistics: null,
})

async function mockSession(page: Page) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: admin }))
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({ json: { required: false, enabled: false } }),
  )
  await page.route("**/api/auth/catalogue-preferences", (route) =>
    route.fulfill({ json: { filter_order: [] } }),
  )
}

test("latest catalogue and facet responses win over delayed requests", async ({ page }) => {
  await mockSession(page)
  let catalogueCalls = 0
  let facetCalls = 0
  await page.route("**/api/models?**", async (route) => {
    catalogueCalls += 1
    if (catalogueCalls === 1) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      await route.fulfill({ json: { items: [model(1, "Stale model")], total: 1, page: 1, page_size: 48 } })
      return
    }
    await route.fulfill({ json: { items: [model(2, "Current model")], total: 1, page: 1, page_size: 48 } })
  })
  await page.route("**/api/models/filters**", async (route) => {
    facetCalls += 1
    if (facetCalls === 1) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      await route.fulfill({ json: filters("Stale creator") })
      return
    }
    await route.fulfill({ json: filters("Current creator") })
  })
  await page.route("**/api/favorite-lists/model-memberships**", (route) => route.fulfill({ json: [] }))

  await page.goto("/")
  await page.getByRole("button", { name: "Sort models" }).click()
  await page.getByRole("option", { name: "Creator: Z–A" }).click()

  await expect(page.getByRole("heading", { name: "Current model" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Stale model" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Creator" })).toBeVisible()
  await expect(page.getByText("Unable to load the catalogue")).toHaveCount(0)
  await expect(page.getByText("Unable to load filters")).toHaveCount(0)
})

test("favorite memberships remain tied to the current catalogue page", async ({ page }) => {
  await mockSession(page)
  let catalogueCalls = 0
  let membershipCalls = 0
  await page.route("**/api/models/filters**", (route) => route.fulfill({ json: filters("Creator") }))
  await page.route("**/api/models?**", (route) => {
    catalogueCalls += 1
    return route.fulfill({
      json: { items: [model(catalogueCalls, `Model ${catalogueCalls}`)], total: 1, page: 1, page_size: 48 },
    })
  })
  await page.route("**/api/favorite-lists/model-memberships**", async (route) => {
    membershipCalls += 1
    if (membershipCalls === 1) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      await route.fulfill({ json: [{ model_id: 1, lists: [{ id: 1, name: "Stale", item_id: 1 }] }] })
      return
    }
    await route.fulfill({ json: [{ model_id: 2, lists: [{ id: 2, name: "Current", item_id: 2 }] }] })
  })

  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Model 1" })).toBeVisible()
  await page.getByRole("button", { name: "Sort models" }).click()
  await page.getByRole("option", { name: "Creator: Z–A" }).click()

  await expect(page.getByRole("heading", { name: "Model 2" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Current" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Stale" })).toHaveCount(0)
})

test("rapid detail changes ignore stale detail and navigation responses", async ({ page }) => {
  await mockSession(page)
  await page.route("**/api/tags", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", (route) => route.fulfill({ json: [] }))
  await page.route(/\/api\/models\/\d+\/navigation.*/, async (route) => {
    const id = Number(route.request().url().match(/models\/(\d+)/)?.[1])
    if (id === 1) await new Promise((resolve) => setTimeout(resolve, 500))
    await route.fulfill({ json: { previous: null, next: id === 2 ? { id: 3, name: "Model 3", variant: null } : null } })
  })
  await page.route(/\/api\/models\/\d+$/, async (route) => {
    const id = Number(route.request().url().match(/models\/(\d+)/)?.[1])
    if (id === 1) await new Promise((resolve) => setTimeout(resolve, 500))
    await route.fulfill({ json: detail(id) })
  })

  await page.goto("/models/1")
  await page.goto("/models/2")

  await expect(page.getByRole("heading", { name: "Model 2" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Model 1" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Next model" })).toHaveAttribute("title", "Next: Model 3")
  await expect(page.getByText("Unable to load the model")).toHaveCount(0)
  await expect(page.getByText("Unable to load navigation")).toHaveCount(0)
  await expect(page.getByText("Loading…")).toHaveCount(0)
})
