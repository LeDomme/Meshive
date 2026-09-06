import { expect, test } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "user", is_active: true, must_change_password: false, permissions: ["catalogue.view", "sources.manage"], source_access: { all_sources: true, source_ids: [] } }

async function mock(page: import("@playwright/test").Page, user = admin) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [] }))
}

test("administration menu supports keyboard escape and outside dismissal", async ({ page }) => {
  await mock(page)
  await page.goto("/admin/sources")
  const menu = page.locator(".account-menu")
  const summary = menu.locator("summary")
  await expect(page.getByRole("link", { name: "Back to Meshive" })).toBeVisible()
  await summary.focus()
  await page.keyboard.press("Enter")
  await expect(menu).toHaveAttribute("open", "")
  await expect(menu.getByText("Administration", { exact: true })).toBeVisible()
  await expect(menu.getByRole("link", { name: "Account settings" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(menu).not.toHaveAttribute("open", "")
  await summary.click()
  await page.locator("h1").click()
  await expect(menu).not.toHaveAttribute("open", "")
})

test("administration menu is hidden without permitted entries on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 700 })
  await mock(page, { ...admin, permissions: [] })
  await page.route("**/api/models/filters**", route => route.fulfill({ json: { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] } }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 48 } }))
  await page.goto("/")
  await page.locator(".account-menu summary").click()
  await expect(page.getByText("Administration", { exact: true })).toHaveCount(0)
  await expect(page.locator(".account-menu")).toBeVisible()
})

test("catalogue keeps administration access in the account menu only", async ({ page }) => {
  await mock(page)
  await page.route("**/api/models/filters**", route => route.fulfill({ json: { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] } }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 48 } }))
  await page.goto("/")
  await expect(page.locator(".catalogue-nav").getByRole("link", { name: "Administration" })).toHaveCount(0)
  await expect(page.locator(".catalogue-nav").getByRole("link", { name: "Tags" })).toHaveCount(0)
  await page.locator(".account-menu summary").click()
  await expect(page.locator(".account-menu").getByText("Administration", { exact: true })).toBeVisible()
})
