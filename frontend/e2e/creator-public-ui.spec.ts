import { expect, test } from "@playwright/test"

const user = {
  id: 1, username: "Viewer", email: null, email_verified: false, role: "user",
  is_active: true, must_change_password: false, permissions: ["catalogue.view"],
  source_access: { all_sources: true, source_ids: [] },
}

test("creator card wraps safely and navigates to the stable profile catalogue filter", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 844 })
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/7/navigation**", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/creators/42", route => route.fulfill({ json: {
    id: 42, display_name: "An exceptionally long creator name that must always stay inside this compact card",
    description: "A deliberately long creator description that wraps within the compact card without pushing its links or actions outside the mobile viewport.", artwork: null, model_count: 2,
    links: [{ id: 1, label: "A very long external creator link label that also wraps safely", url: "https://example.test" }, { id: 2, label: "Second creator link", url: "https://example.org" }, { id: 3, label: "Third creator link", url: "https://example.net" }],
    primary_link: { id: 1, label: "A very long external creator link label that also wraps safely", url: "https://example.test" },
  } }))
  await page.route("**/api/models/7", route => route.fulfill({ json: {
    id: 7, name: "Visible model", variants: [], variant: null, creator: "Long creator", creator_profile_id: 42, creator_links: [{ id: 1, label: "Legacy link", url: "https://example.test" }], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: "Visible model", images: [], archives: [], archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null, tags: [],
  } }))
  await page.goto("/models/7")
  const card = page.getByLabel("Creator")
  await expect(card.locator("img")).toHaveAttribute("src", "/favorite-fallbacks/favorite-creator.webp")
  await expect(card.getByText("An exceptionally long creator name that must always stay inside this compact card")).toBeVisible()
  await expect(card.locator(".creator-description")).toContainText("A deliberately long creator description")
  await expect(card.getByRole("link", { name: "View all" })).toHaveAttribute("href", "/?creator_profile_id=42")
  await expect(card.getByRole("link", { name: "View all" })).toHaveCSS("text-decoration-line", "none")
  await expect(card.locator(".creator-artwork")).toHaveAttribute("href", "/?creator_profile_id=42")
  await expect(card.getByRole("link", { name: "An exceptionally long creator name that must always stay inside this compact card" })).toHaveAttribute("href", "/?creator_profile_id=42")
  await expect(card.getByRole("link", { name: "An exceptionally long creator name that must always stay inside this compact card" })).toHaveCSS("text-decoration-line", "none")
  await expect(card.locator(".creator-card-links")).toHaveCount(1)
  await expect(card.locator(".creator-card-links a")).toHaveCount(3)
  await expect(card.locator(".creator-card-links a").first()).toHaveCSS("text-decoration-line", "none")
  const topBox = await card.locator(".creator-card-top").boundingBox()
  const descriptionBox = await card.locator(".creator-description").boundingBox()
  const linksBox = await card.locator(".creator-card-links").boundingBox()
  expect(topBox).not.toBeNull()
  expect(descriptionBox).not.toBeNull()
  expect(linksBox).not.toBeNull()
  expect(descriptionBox!.y).toBeGreaterThanOrEqual(topBox!.y + topBox!.height)
  expect(linksBox!.y).toBeGreaterThanOrEqual(descriptionBox!.y + descriptionBox!.height)
  await expect(page.getByText("Creator links", { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test("profile-ID catalogue filters show the profile name and can be cleared", async ({ page }) => {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: {
    models: [], creators: [{ value: "Canonical Creator", count: 2 }],
    creator_profiles: [{
      id: 42,
      display_name: "Canonical Creator",
      count: 2,
      aliases: ["Legacy Alias"],
    }],
    franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [],
  } }))
  await page.route("**/api/models?**", route => route.fulfill({ json: {
    items: [{ id: 7, name: "Alias model", variants: [], variant: null, creator: "Legacy Alias", creator_profile_id: 42, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: null, archive_size_bytes: null, archive_count: 0, thumbnail_url: null, tags: [] }], total: 1, page: 1, page_size: 48,
  } }))
  await page.goto("/?creator_profile_id=42&sort=name_asc")
  const creatorFilter = page.getByRole("button", { name: "Creator" })
  await expect(creatorFilter).toContainText("Canonical Creator")
  await expect(page.getByText("Alias model")).toBeVisible()
  await creatorFilter.click()
  await page.getByRole("searchbox", { name: "Search creator" }).fill("legacy")
  await expect(page.getByRole("option", { name: "Canonical Creator" })).toHaveCount(1)
  await page.getByRole("option", { name: "Canonical Creator" }).click()
  await expect(page).toHaveURL(/creator_profile_id=42/)
  await creatorFilter.click()
  await page.getByRole("option", { name: "All creators" }).click()
  await expect(page).not.toHaveURL(/creator_profile_id=/)
  await page.goto("/?creator=Legacy%20Alias&sort=name_asc")
  await expect(page.getByRole("button", { name: "Creator" })).toContainText("Legacy Alias")
})
