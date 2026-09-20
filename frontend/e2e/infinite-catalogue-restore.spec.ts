import { expect, test, type Page } from "@playwright/test"

const user = { id: 1, username: "Curator", email: null, email_verified: false, role: "curator", is_active: true, must_change_password: false, permissions: ["catalogue.view"], source_access: { all_sources: true, source_ids: [] } }
const filters = { models: [], creators: [{ value: "Ada", count: 240 }, { value: "Bea", count: 240 }], franchises: [], series: [], collections: [], sources: [{ id: 1, name: "Library", count: 240 }], statuses: [], tags: [] }

function model(pageNumber: number, itemNumber: number, creator = "Ada") {
  const id = (pageNumber - 1) * 48 + itemNumber
  return { id, name: `${creator} page ${pageNumber} model ${itemNumber}`, variants: [], variant: null, creator, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }
}

function detail(id: number) {
  return { id, name: `Detail ${id}`, variants: [], variant: null, creator: "Ada", creator_links: [], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: `Model ${id}`, images: [], archives: [], archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null, tags: [] }
}

async function mockInfiniteCatalogue(
  page: Page,
  savedViews: unknown[] = [],
  modelRequests: number[] = [],
  includeDuplicateOnSecondPage = false,
) {
  let preferences = { filter_order: [], action_order: [], navigation_mode: "pagination" }
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/auth/catalogue-preferences", route => {
    if (route.request().method() === "PUT") preferences = route.request().postDataJSON()
    return route.fulfill({ json: preferences })
  })
  await page.route("**/api/saved-views", route => route.fulfill({ json: savedViews }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route(/\/api\/models\/\d+\/navigation.*/, route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route(/\/api\/models\/\d+$/, route => route.fulfill({ json: detail(Number(route.request().url().match(/models\/(\d+)/)?.[1])) }))
  await page.route("**/api/models?**", route => {
    const url = new URL(route.request().url())
    const requestedPage = Number(url.searchParams.get("page") || "1")
    modelRequests.push(requestedPage)
    const creator = url.searchParams.get("creator") || "Ada"
    const items = Array.from({ length: 48 }, (_, index) => model(requestedPage, index + 1, creator))
    if (includeDuplicateOnSecondPage && requestedPage === 2) items[0] = model(1, 1, creator)
    return route.fulfill({ json: { items, total: 4000, page: requestedPage, page_size: 48 } })
  })
}

async function mockIntersectionObserver(page: Page) {
  await page.addInitScript(() => {
    class TestIntersectionObserver {
      constructor(private readonly callback: IntersectionObserverCallback) {}

      observe(target: Element) {
        ;(window as Window & { triggerInfiniteSentinel?: () => void }).triggerInfiniteSentinel = () => {
          this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
        }
      }

      disconnect() {}
      unobserve() {}
      takeRecords() { return [] }
      root = null
      rootMargin = "0px"
      thresholds = []
    }

    window.IntersectionObserver = TestIntersectionObserver as unknown as typeof IntersectionObserver
  })
}

async function enableInfiniteAndLoadThreePages(page: Page) {
  await page.getByRole("switch", { name: "Infinite scroll" }).click()
  await expect(page.getByRole("link", { name: "Ada page 1 model 1", exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Load more" }).click()
  await expect(page.getByRole("link", { name: "Ada page 2 model 1", exact: true })).toBeVisible()
  await page.getByRole("button", { name: "Load more" }).click()
  await expect(page.getByRole("link", { name: "Ada page 3 model 1", exact: true })).toBeVisible()
}

async function loadInfiniteCatalogueTo(page: Page, itemCount: number) {
  const cards = page.locator(".model-card")
  const loadMore = page.getByRole("button", { name: "Load more" })
  let loadedCount = await cards.count()
  while (loadedCount < itemCount) {
    await loadMore.evaluate((button) => {
      if ((button as HTMLButtonElement).disabled) throw new Error("Load more is disabled")
      ;(button as HTMLButtonElement).click()
    })
    loadedCount = Math.min(itemCount, loadedCount + 48)
    await expect(cards).toHaveCount(loadedCount)
  }
  await expect(cards).toHaveCount(itemCount)
}

async function expectUniqueModelCards(page: Page) {
  const modelIds = await page.locator(".model-title-link").evaluateAll((links) =>
    links.map((link) => new URL((link as HTMLAnchorElement).href).pathname),
  )
  expect(new Set(modelIds).size).toBe(modelIds.length)
}

async function visitCatalogueScrollPositions(page: Page) {
  await page.evaluate(async () => {
    const step = window.innerHeight * 4
    for (let top = 0; top < document.documentElement.scrollHeight; top += step) {
      window.scrollTo({ top, behavior: "auto" })
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
    }
  })
}

async function scrollNearInfiniteSentinel(page: Page) {
  await page.locator(".infinite-sentinel").scrollIntoViewIfNeeded()
  await page.evaluate(() => window.scrollBy(0, -180))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0)
}

async function openVisibleModelDetail(page: Page) {
  const link = page.locator(".model-title-link").first()
  await expect(link).toBeVisible()
  await link.click()
  await expect(page).toHaveURL(/\/models\/\d+/)
}

test("browser back restores infinite batches, scroll position, and automatic loading", async ({ page }) => {
  await mockIntersectionObserver(page)
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [], modelRequests)
  await page.goto("/")
  await enableInfiniteAndLoadThreePages(page)
  await visitCatalogueScrollPositions(page)
  await scrollNearInfiniteSentinel(page)
  const scrollY = await page.evaluate(() => window.scrollY)

  await openVisibleModelDetail(page)
  modelRequests.length = 0
  await page.goBack()

  await expect(page.getByRole("link", { name: "Ada page 3 model 1", exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(scrollY - 4)
  expect(modelRequests).toEqual([])
  await page.evaluate(() => (window as Window & { triggerInfiniteSentinel: () => void }).triggerInfiniteSentinel())
  await expect(page.getByRole("link", { name: "Ada page 4 model 1", exact: true })).toBeVisible()
})

test("large infinite catalogue keeps card structure and restores cached batches", async ({ page }) => {
  await mockIntersectionObserver(page)
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [], modelRequests)
  await page.goto("/")
  await page.getByRole("switch", { name: "Infinite scroll" }).click()

  await loadInfiniteCatalogueTo(page, 528)
  await expectUniqueModelCards(page)
  await expect(page.locator(".model-card").first()).toHaveCSS("content-visibility", "auto")
  await expect(page.locator(".model-card img").first()).toHaveAttribute("loading", "lazy")
  await expect(page.locator(".model-card img").first()).toHaveAttribute("decoding", "async")

  await loadInfiniteCatalogueTo(page, 1008)
  await expectUniqueModelCards(page)
  await visitCatalogueScrollPositions(page)
  await scrollNearInfiniteSentinel(page)
  const scrollY = await page.evaluate(() => window.scrollY)
  await openVisibleModelDetail(page)
  modelRequests.length = 0

  await page.goBack()

  await expect(page.locator(".model-card")).toHaveCount(1008)
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(scrollY - 4)
  expect(modelRequests).toEqual([])
  await expectUniqueModelCards(page)
})

test("infinite item index drops duplicate batches and resets for filters and mode changes", async ({ page }) => {
  await mockInfiniteCatalogue(page, [], [], true)
  await page.goto("/")
  await page.getByRole("switch", { name: "Infinite scroll" }).click()
  await page.getByRole("button", { name: "Load more" }).click()
  await expect(page.locator(".model-card")).toHaveCount(95)
  await expectUniqueModelCards(page)

  await page.getByRole("switch", { name: "Infinite scroll" }).click()
  await expect(page.locator(".model-card")).toHaveCount(48)
  await page.getByRole("switch", { name: "Infinite scroll" }).click()
  await expect(page.locator(".model-card")).toHaveCount(48)

  await page.getByRole("button", { name: "Creator" }).click()
  await page.getByRole("option", { name: /^Bea/ }).click()
  await expect(page.getByRole("link", { name: "Bea page 1 model 1", exact: true })).toBeVisible()
  await expect(page.locator(".model-card")).toHaveCount(48)
  await expectUniqueModelCards(page)
})

test("catalogue back restores a saved view and infinite automatic loading", async ({ page }) => {
  await mockIntersectionObserver(page)
  const savedView = { id: 1, name: "Ada view", state: { search: "", model: "", creator: "Ada", creator_profile_id: "", franchise: "", series: "", collection: "", source_id: "1", tag_id: "", status: "", sort: "name_asc" }, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:00Z" }
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [savedView], modelRequests)
  await page.goto("/")
  await page.getByRole("button", { name: "Saved views" }).click()
  await page.getByRole("option", { name: "Ada view" }).click()
  await expect(page).toHaveURL(/creator=Ada&source_id=1&sort=name_asc$/)
  await expect(page.getByRole("link", { name: "Ada page 1 model 1", exact: true })).toBeVisible()
  await enableInfiniteAndLoadThreePages(page)
  await visitCatalogueScrollPositions(page)
  await scrollNearInfiniteSentinel(page)
  const scrollY = await page.evaluate(() => window.scrollY)

  await openVisibleModelDetail(page)
  modelRequests.length = 0
  await expect(page.getByRole("link", { name: "Back to catalogue" })).toBeVisible()
  await page.getByRole("link", { name: "Back to catalogue" }).click()

  await expect(page.getByRole("button", { name: "Saved views" })).toContainText("Ada view")
  await expect(page.getByRole("link", { name: "Ada page 3 model 1", exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(scrollY - 4)
  expect(modelRequests).toEqual([])
  await page.evaluate(() => (window as Window & { triggerInfiniteSentinel: () => void }).triggerInfiniteSentinel())
  await expect(page.getByRole("link", { name: "Ada page 4 model 1", exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Creator" }).click()
  await page.getByRole("option", { name: /^Bea/ }).click()
  await expect(page.getByRole("link", { name: "Bea page 1 model 1", exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: "Ada page 3 model 1", exact: true })).toHaveCount(0)
})

test("reload falls back to restoring the previously loaded infinite batches", async ({ page }) => {
  await mockIntersectionObserver(page)
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [], modelRequests)
  await page.goto("/")
  await enableInfiniteAndLoadThreePages(page)
  await scrollNearInfiniteSentinel(page)

  await openVisibleModelDetail(page)
  await page.reload()
  modelRequests.length = 0
  await page.goto("/?sort=name_asc&page=3")

  await expect(page.getByRole("link", { name: "Ada page 3 model 1", exact: true })).toBeVisible()
  await expect.poll(() => modelRequests).toEqual([1, 2, 3])
})

test("pagination browser back restores a high page directly", async ({ page }) => {
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [], modelRequests)
  await page.goto("/?creator=Ada&page=77")
  await expect(page.getByRole("link", { name: "Ada page 77 model 1", exact: true })).toBeVisible()

  await openVisibleModelDetail(page)
  modelRequests.length = 0
  await page.goBack()

  await expect(page.getByRole("link", { name: "Ada page 77 model 1", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/page=77/)
  await expect.poll(() => modelRequests).toEqual([77])
})

test("pagination catalogue back restores a saved view high page directly", async ({ page }) => {
  const savedView = { id: 1, name: "Ada view", state: { search: "", model: "", creator: "Ada", creator_profile_id: "", franchise: "", series: "", collection: "", source_id: "1", tag_id: "", status: "", sort: "name_asc" }, created_at: "2026-09-18T00:00:00Z", updated_at: "2026-09-18T00:00:00Z" }
  const modelRequests: number[] = []
  await mockInfiniteCatalogue(page, [savedView], modelRequests)
  await page.goto("/")
  await page.getByRole("button", { name: "Saved views" }).click()
  await page.getByRole("option", { name: "Ada view" }).click()
  await expect(page).toHaveURL(/creator=Ada&source_id=1&sort=name_asc$/)
  await page.goto("/?creator=Ada&source_id=1&sort=name_asc&page=77")
  await expect(page.getByRole("link", { name: "Ada page 77 model 1", exact: true })).toBeVisible()

  await openVisibleModelDetail(page)
  modelRequests.length = 0
  await page.getByRole("link", { name: "Back to catalogue" }).click()

  await expect(page.getByRole("button", { name: "Saved views" })).toContainText("Ada view")
  await expect(page.getByRole("link", { name: "Ada page 77 model 1", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/page=77/)
  await expect.poll(() => modelRequests).toEqual([77])
})
