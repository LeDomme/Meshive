import { expect, test, type Page } from "@playwright/test"

const user = {
  id: 1,
  username: "Curator",
  email: null,
  email_verified: false,
  role: "curator",
  is_active: true,
  must_change_password: false,
  permissions: ["catalogue.view"],
  source_access: { all_sources: true, source_ids: [] },
}

const defaultFilterOrder = ["model", "variant", "creator", "franchise", "series", "source", "tag", "status", "sort"]
const defaultActionOrder = ["selection", "saved_views", "navigation"]

async function mockAccount(page: Page) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/auth/sessions", route => route.fulfill({ json: [] }))
}

test("account resets catalogue layout while preserving navigation mode", async ({ page }) => {
  let preferences = {
    filter_order: ["sort", "model", "variant", "creator", "franchise", "series", "source", "tag", "status"],
    action_order: ["navigation", "saved_views", "selection"],
    navigation_mode: "infinite",
  }
  await mockAccount(page)
  await page.route("**/api/auth/catalogue-preferences", async route => {
    if (route.request().method() === "PUT") preferences = route.request().postDataJSON()
    await route.fulfill({ json: preferences })
  })
  await page.route("**/api/saved-views**", route => route.fulfill({ json: [{ id: 3, name: "Ada view" }] }))

  await page.goto("/account")
  await expect(page.getByRole("heading", { name: "Catalogue preferences" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Saved views" })).toBeVisible()
  await expect(page.getByText("Ada view", { exact: true })).toBeVisible()

  await expect(page.getByRole("button", { name: "Reset navigation mode" })).toHaveCount(0)
  await page.getByRole("button", { name: "Reset" }).click()
  await expect.poll(() => preferences).toEqual({
    filter_order: defaultFilterOrder,
    action_order: defaultActionOrder,
    navigation_mode: "infinite",
  })
  await expect(page.getByText("Ada view", { exact: true })).toBeVisible()
})

test("account manages saved views without reloading", async ({ page }) => {
  let savedViews = [{ id: 3, name: "Ada view", created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z" }]
  await mockAccount(page)
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [], action_order: [], navigation_mode: "pagination" } }))
  await page.route("**/api/saved-views**", async route => {
    const method = route.request().method()
    if (method === "GET") return route.fulfill({ json: savedViews })
    if (method === "PUT") {
      savedViews = [{ ...savedViews[0], name: route.request().postDataJSON().name }]
      return route.fulfill({ json: savedViews[0] })
    }
    if (method === "DELETE") {
      savedViews = []
      return route.fulfill({ status: 204 })
    }
    return route.fulfill({ status: 405 })
  })

  await page.goto("/account")
  page.once("dialog", dialog => dialog.accept("Renamed view"))
  await page.getByRole("button", { name: "Rename" }).click()
  await expect(page.getByText("Renamed view", { exact: true })).toBeVisible()
  page.once("dialog", dialog => dialog.accept())
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByText("No saved views yet.")).toBeVisible()
})

test("account shows saved-view API errors", async ({ page }) => {
  await mockAccount(page)
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [], action_order: [], navigation_mode: "pagination" } }))
  await page.route("**/api/saved-views**", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: [{ id: 3, name: "Ada view" }] })
    return route.fulfill({ status: 409, json: { detail: "A saved view with this name already exists" } })
  })

  await page.goto("/account")
  page.once("dialog", dialog => dialog.accept("Duplicate"))
  await page.getByRole("button", { name: "Rename" }).click()
  await expect(page.getByRole("alert")).toContainText("A saved view with this name already exists")
})
