import { expect, test } from "@playwright/test"

const user = {
  id: 1, username: "Viewer", email: null, email_verified: false, role: "user",
  is_active: true, must_change_password: false, permissions: ["catalogue.view"],
  source_access: { all_sources: true, source_ids: [] },
}

test("creator detail uses its stable profile URL and paginates its scoped catalogue", async ({ page }) => {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/creators/42", route => route.fulfill({ json: {
    id: 42, display_name: "Renamed Creator", description: null, artwork: null,
    links: [{ id: 1, label: "Website", url: "https://example.test" }],
    primary_link: { id: 1, label: "Website", url: "https://example.test" }, model_count: 25,
  } }))
  await page.route("**/api/models?creator_profile_id=42**", route => route.fulfill({ json: {
    items: [{ id: 7, name: "Visible model", variant: null, thumbnail_url: null }], total: 25, page: 1, page_size: 24,
  } }))
  await page.goto("/creators/42")
  await expect(page.getByRole("heading", { name: "Renamed Creator" })).toBeVisible()
  await expect(page.getByText("25 visible models")).toBeVisible()
  await expect(page.getByRole("link", { name: "Visible model" })).toHaveAttribute("href", "/models/7")
  await expect(page.getByRole("link", { name: "Website ↗" })).toHaveAttribute("rel", "noopener noreferrer")
})

test("creator detail treats an inaccessible profile as not found", async ({ page }) => {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/creators/404", route => route.fulfill({ status: 404, json: { detail: "Creator not found" } }))
  await page.goto("/creators/404")
  await expect(page.getByRole("heading", { name: "Creator not found" })).toBeVisible()
})

test("creator card wraps long names and uses the shared fallback artwork on narrow screens", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 844 })
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/7/navigation**", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/creators/42", route => route.fulfill({ json: {
    id: 42, display_name: "An exceptionally long creator name that must always stay inside this compact card",
    description: null, artwork: null, model_count: 2,
    links: [{ id: 1, label: "A very long external creator link label that also wraps safely", url: "https://example.test" }],
    primary_link: { id: 1, label: "A very long external creator link label that also wraps safely", url: "https://example.test" },
  } }))
  await page.route("**/api/models/7", route => route.fulfill({ json: {
    id: 7, name: "Visible model", variant: null, creator: "Long creator", creator_profile_id: 42, creator_links: [{ id: 1, label: "Legacy link", url: "https://example.test" }], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: "Visible model", images: [], archives: [], archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null, tags: [],
  } }))
  await page.goto("/models/7")
  const card = page.getByLabel("Creator")
  await expect(card.locator("img")).toHaveAttribute("src", "/favorite-fallbacks/favorite-creator.webp")
  await expect(card.getByText("An exceptionally long creator name that must always stay inside this compact card")).toBeVisible()
  await expect(card.getByRole("link", { name: "View all models" })).toHaveAttribute("href", "/creators/42")
  await expect(page.getByText("Creator links", { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
