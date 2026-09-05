import { expect, test } from "@playwright/test"

function user(permissions: string[], allSources = true) {
  return {
    id: 1,
    username: "Manager",
    email: null,
    email_verified: false,
    role: "user",
    is_active: true,
    must_change_password: false,
    permissions,
    source_access: { all_sources: allSources, source_ids: [] },
  }
}

async function mockAuth(page: import("@playwright/test").Page, permissions: string[], allSources = true) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user(permissions, allSources) }))
}

test("metadata managers see only Metadata and load no tag administration APIs", async ({ page }) => {
  let tagRequest = false
  await mockAuth(page, ["metadata.manage"])
  await page.route("**/api/admin/creator-links", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/metadata", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags**", route => { tagRequest = true; return route.fulfill({ status: 403 }) })

  await page.goto("/admin/metadata")
  await expect(page.getByRole("heading", { name: "Metadata", exact: true })).toBeVisible()
  await page.locator(".account-menu summary").click()
  await expect(page.getByRole("link", { name: "Metadata" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Tags" })).toHaveCount(0)
  expect(tagRequest).toBe(false)
})

test("tag-rule managers load only assignment rules", async ({ page }) => {
  let legacyRequest = false
  await mockAuth(page, ["tag_rules.manage"])
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/folder-tag-rules", route => { legacyRequest = true; return route.fulfill({ status: 403 }) })
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [{ id: 1, name: "Bust", color: null, description: null }] }))
  await page.route("**/api/admin/tags/1/assignment-rules", route => route.fulfill({ json: [] }))

  await page.goto("/admin/tags")
  await expect(page.getByRole("heading", { name: "Assignment rules" })).toBeVisible()
  await expect(page.locator("h2", { hasText: "Tags" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Folder tag rules" })).toHaveCount(0)
  expect(legacyRequest).toBe(false)
})

test("tag managers load tag administration but no assignment rules", async ({ page }) => {
  let assignmentRequest = false
  await mockAuth(page, ["tags.manage"])
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags/1/assignment-rules", route => { assignmentRequest = true; return route.fulfill({ status: 403 }) })

  await page.goto("/admin/tags")
  await expect(page.locator("h2", { hasText: "Tags" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Assignment rules" })).toHaveCount(0)
  expect(assignmentRequest).toBe(false)
})

test("metadata and tag routes require their permissions and all-sources access", async ({ page }) => {
  await mockAuth(page, ["metadata.manage"], false)
  await page.goto("/admin/metadata")
  await expect(page).not.toHaveURL(/\/admin\/metadata/)
  await page.goto("/admin/tags")
  await expect(page).not.toHaveURL(/\/admin\/tags/)
})
