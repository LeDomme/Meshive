import { expect, test, type Page } from "@playwright/test"

const user = {
  id: 1, username: "Curator", email: null, email_verified: false, role: "curator",
  is_active: true, must_change_password: false,
  permissions: ["catalogue.view", "models.tags"], source_access: { all_sources: true, source_ids: [] },
}
const images = [1, 2, 3].map((id) => ({
  id, filename: `picture-${id}.jpg`, format: "jpg", size_bytes: 1,
  is_primary: id === 1, url: `/images/${id}.jpg`,
}))
const tags = [
  { id: 7, name: "Existing", color: null, description: null },
  { id: 8, name: "Added", color: "#5eead4", description: null },
]

async function mockDetail(page: Page) {
  let assignedTags = [tags[0]]
  await page.route("**/api/setup/status", (route) => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: user }))
  await page.route("**/api/tags", (route) => route.fulfill({ json: tags }))
  await page.route("**/api/favorite-lists/model-memberships**", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", (route) => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", (route) => route.fulfill({ json: {
    id: 1, name: "Tagged gallery model", variant: null, creator: null, creator_links: [],
    franchise: null, series: null, collection: null, status: "available", source_id: 1,
    source_name: "Library", relative_path: "Tagged gallery", images, archives: [],
    archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null,
    tags: assignedTags,
  } }))
  await page.route("**/api/admin/models/1/tags/8", (route) => {
    assignedTags = route.request().method() === "PUT" ? [tags[0], tags[1]] : [tags[0]]
    return route.fulfill({ status: 204 })
  })
}

test("tag changes retain the selected gallery image and open lightbox", async ({ page }) => {
  await mockDetail(page)
  await page.goto("/models/1")
  await page.getByRole("button", { name: "Next picture" }).click()
  await expect(page.getByRole("img", { name: "Tagged gallery model — picture-2.jpg" })).toBeVisible()
  const initialUrl = page.url()

  await page.getByLabel("Tag to add").selectOption("8")
  await page.getByRole("button", { name: "Add", exact: true }).click()
  await expect(page.getByRole("link", { name: "Added" })).toBeVisible()
  await expect(page.getByRole("img", { name: "Tagged gallery model — picture-2.jpg" })).toBeVisible()
  expect(page.url()).toBe(initialUrl)

  await page.getByRole("button", { name: "Open image viewer" }).click()
  await expect(page.getByRole("dialog", { name: "picture-2.jpg" })).toBeVisible()
  await page.getByRole("dialog").getByRole("button", { name: "Next picture" }).click()
  await expect(page.getByRole("dialog").getByRole("img", { name: "Tagged gallery model — picture-3.jpg" })).toBeVisible()

  await page.getByRole("button", { name: "Remove Added tag" }).evaluate((button) => button.click())
  await expect(page.getByRole("link", { name: "Added" })).toHaveCount(0)
  await expect(page.getByRole("dialog", { name: "picture-3.jpg" })).toBeVisible()
  await expect(page.getByRole("dialog").getByRole("img", { name: "Tagged gallery model — picture-3.jpg" })).toBeVisible()
  expect(page.url()).toBe(initialUrl)
})

test("a failed tag mutation preserves the detail state and shows its error", async ({ page }) => {
  await mockDetail(page)
  await page.route("**/api/admin/models/1/tags/8", (route) => route.fulfill({ status: 500, json: { detail: "Tag update failed" } }))
  await page.goto("/models/1")
  await page.getByRole("button", { name: "Next picture" }).click()
  await page.getByLabel("Tag to add").selectOption("8")
  await page.getByRole("button", { name: "Add", exact: true }).click()

  await expect(page.getByRole("alert")).toContainText("Tag update failed")
  await expect(page.getByRole("link", { name: "Existing" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Added" })).toHaveCount(0)
  await expect(page.getByRole("img", { name: "Tagged gallery model — picture-2.jpg" })).toBeVisible()
})
