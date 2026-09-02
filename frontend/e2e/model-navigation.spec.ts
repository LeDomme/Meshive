import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const detail = (id: number) => ({ id, name: `Model ${id}`, variant: null, creator: null, creator_links: [], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: `Model ${id}`, images: [], archives: [], archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null, tags: [] })

test("next model preserves catalogue context for navigation and back link", async ({ page }) => {
  const navigationRequests: string[] = []
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route(/\/api\/models\/\d+\/navigation.*/, route => { navigationRequests.push(route.request().url()); return route.fulfill({ json: { previous: { id: 1, name: "Model 1", variant: null }, next: { id: 2, name: "Model 2", variant: null } } }) })
  await page.route(/\/api\/models\/\d+$/, route => route.fulfill({ json: detail(Number(route.request().url().match(/models\/(\d+)/)?.[1])) }))
  await page.goto("/models/1?creator=Ada&sort=creator_desc")
  await expect.poll(() => navigationRequests.some(url => url.includes("creator=Ada") && url.includes("sort=creator_desc"))).toBe(true)
  await page.getByRole("button", { name: "Next model" }).click()
  await expect(page).toHaveURL(/\/models\/2\?creator=Ada&sort=creator_desc$/)
  await expect(page.getByRole("link", { name: "Back to catalogue" })).toHaveAttribute("href", "/?creator=Ada&sort=creator_desc")
})
