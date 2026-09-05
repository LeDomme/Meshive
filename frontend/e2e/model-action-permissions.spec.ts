import { expect, test, type Page } from "@playwright/test"

const model = {
  id: 1,
  name: "Action model",
  variant: null,
  creator: null,
  creator_links: [],
  franchise: null,
  series: null,
  collection: null,
  status: "incomplete",
  source_id: 1,
  source_name: "Library",
  relative_path: "Action model",
  images: [{ id: 3, filename: "cover.jpg", format: "jpg", size_bytes: 1, is_primary: false, url: "/cover.jpg" }],
  archives: [],
  archive_bundle_download_url: null,
  recent_scan_issues: [{ code: "missing-image", message: "Image missing", created_at: "2026-01-01T00:00:00Z" }],
  archive_statistics: { image_files: 1, stl_files: 1, chitubox_files: 0, lychee_files: 0, exported_images: 1 },
  tags: [{ id: 7, name: "Visible", color: null, description: null }],
}

async function mockModel(page: Page, permissions: string[]) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: 1, username: "Custom", email: null, email_verified: false, role: "user", is_active: true, must_change_password: false, permissions, source_access: { all_sources: true, source_ids: [] } } }))
  await page.route("**/api/tags", route => route.fulfill({ json: model.tags }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
}

test("individual model action permissions expose only their action", async ({ page }) => {
  await mockModel(page, ["catalogue.view", "models.primary_image"])
  let primaryCalled = false
  await page.route("**/api/admin/models/1/images/3/primary", route => {
    primaryCalled = true
    return route.fulfill({ json: { primary_image_id: 3 } })
  })
  await page.goto("/models/1")

  await expect(page.getByRole("button", { name: "Use as primary" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Rescan model" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Rebuild archive images" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Reset pictures" })).toHaveCount(0)
  await page.getByRole("button", { name: "Use as primary" }).click()
  expect(primaryCalled).toBe(true)
})

test("tag permission exposes tag controls without other model actions", async ({ page }) => {
  await mockModel(page, ["catalogue.view", "models.tags"])
  let tagRemoved = false
  await page.route("**/api/admin/models/1/tags/7", route => {
    tagRemoved = true
    return route.fulfill({ status: 204 })
  })
  await page.goto("/models/1")

  await expect(page.getByRole("button", { name: "Remove Visible tag" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Add" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Use as primary" })).toHaveCount(0)
  await page.getByRole("button", { name: "Remove Visible tag" }).click()
  expect(tagRemoved).toBe(true)
})

test("rescan permission exposes only the rescan action", async ({ page }) => {
  await mockModel(page, ["catalogue.view", "models.rescan"])
  let rescanCalled = false
  await page.route("**/api/admin/models/1/rescan", route => {
    rescanCalled = true
    return route.fulfill({ json: {} })
  })
  await page.goto("/models/1")

  await expect(page.getByRole("button", { name: "Rescan model" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Use as primary" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Rebuild archive images" })).toHaveCount(0)
  await page.getByRole("button", { name: "Rescan model" }).click()
  expect(rescanCalled).toBe(true)
})

test("users without model action permissions see no action controls", async ({ page }) => {
  await mockModel(page, ["catalogue.view"])
  await page.goto("/models/1")

  await expect(page.getByRole("button", { name: "Use as primary" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Rescan model" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Remove Visible tag" })).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Action model" })).toBeVisible()
})

test("maintenance permission exposes maintenance status and scan issues", async ({ page }) => {
  await mockModel(page, ["catalogue.view", "catalogue.view_maintenance"])
  await page.goto("/models/1")

  await expect(page.getByText("incomplete", { exact: true })).toBeVisible()
  await expect(page.getByText("Recent scan issues (1)")).toBeVisible()
  await page.getByText("Recent scan issues (1)").click()
  await expect(page.getByRole("button", { name: "Clear history" })).toBeVisible()
  await expect(page.getByText("Exportable archive images")).toBeVisible()
})
