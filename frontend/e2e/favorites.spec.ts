import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false, permissions: ["catalogue.view"], source_access: { all_sources: true, source_ids: [] } }
const model = { id: 1, name: "Saved model", variant: null, creator: null, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", archive_format: "7z", archive_size_bytes: 1, archive_count: 1, thumbnail_url: null, tags: [] }
const filters = { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }

test("favorite membership persists after a catalogue reload", async ({ page }) => {
  let saved = false
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [] } }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: filters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [model], total: 1, page: 1, page_size: 48 } }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [{ model_id: 1, lists: saved ? [{ id: 4, name: "Later", item_count: 1, item_id: 9 }] : [] }] }))
  await page.route("**/api/favorite-lists", route => route.fulfill({ json: [{ id: 4, name: "Later", item_count: 0 }] }))
  await page.route("**/api/favorite-lists/4/items", async route => { expect(route.request().postDataJSON()).toEqual({ entity_type: "model", model_id: 1 }); saved = true; await route.fulfill({ json: { id: 9 } }) })
  await page.goto("/")
  await page.getByRole("button", { name: "Save" }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByRole("status")).toContainText("Saved")
  await page.reload()
  await expect(page.getByRole("button", { name: "Later" })).toBeVisible()
})
