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
  await page.route("**/api/admin/tags/1/assignment-rules", route => route.fulfill({ json: [{
    id: 8, legacy_kind: "automatic_tag_rule", library_source_id: null,
    match_mode: "contains", pattern: "chitu", path_value: null, path_relation: null,
    enabled: true, targets: [{ target_type: "archive_entry_path", folder_segment: false }],
    match_count: 1,
  }] }))

  await page.goto("/admin/tags")
  await expect(page.getByRole("heading", { name: "Assignment rules" })).toBeVisible()
  await expect(page.getByRole("article").getByText("Text contains", { exact: true })).toBeVisible()
  await expect(page.getByRole("article").getByRole("button", { name: "Edit" })).toBeVisible()
  await expect(page.getByRole("article").getByRole("button", { name: "Re-evaluate" })).toBeVisible()
  await expect(page.getByRole("article").getByRole("button", { name: "Delete" })).toBeVisible()
  await expect(page.getByText("Migrated", { exact: true })).toBeVisible()
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

test("TagsView keeps selection, create and edit states separate and keyboard accessible", async ({ page }) => {
  await mockAuth(page, ["tags.manage"])
  let tags = [
    { id: 1, name: "First", color: "#5eead4", description: "First tag" },
    { id: 2, name: "Second", color: "#60a5fa", description: null },
  ]
  await page.route("**/api/admin/tags", async route => {
    if (route.request().method() === "POST") {
      tags = [...tags, { id: 3, name: "Created", color: "#5eead4", description: null }]
      await route.fulfill({ status: 201, json: tags[2] })
      return
    }
    await route.fulfill({ json: tags })
  })

  await page.goto("/admin/tags")
  const first = page.getByRole("button", { name: /First/ })
  await expect(first).toHaveClass(/selected/)
  await page.getByRole("button", { name: /Second/ }).focus()
  await expect(page.getByRole("button", { name: /Second/ })).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(page.getByRole("heading", { name: "Second" })).toBeVisible()
  await page.getByRole("button", { name: "Create tag" }).click()
  await expect(page.getByRole("heading", { name: "Create tag" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Edit tag" })).toHaveCount(0)
  await page.getByLabel("Name").fill("Created")
  await page.getByRole("button", { name: "Create tag", exact: true }).last().click()
  await expect(page.getByRole("status")).toContainText("Tag created")
  await expect(page.getByRole("heading", { name: "Created" })).toBeVisible()
})

test("TagsView provides rule feedback, confirmation and responsive rule cards", async ({ page }) => {
  await mockAuth(page, ["tags.manage", "tag_rules.manage"])
  const tag = { id: 1, name: "Bust", color: null, description: null }
  const rule = { id: 8, legacy_kind: "automatic_tag_rule", library_source_id: null, match_mode: "contains", pattern: "chitu", path_value: null, path_relation: null, enabled: true, targets: [{ target_type: "archive_entry_path", folder_segment: false }], match_count: 1 }
  let updateRequests = 0
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags/1/assignment-rules", route => route.fulfill({ json: [rule] }))
  await page.route("**/api/admin/tag-assignment-rules/8", async route => {
    updateRequests += 1
    await route.fulfill({ json: { ...rule, enabled: false } })
  })
  await page.route("**/api/admin/tag-assignment-rules/preview", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [tag] }))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/admin/tags")
  await expect(page.getByRole("article")).toBeVisible()
  await page.getByRole("button", { name: "Disable" }).click()
  await expect(page.getByRole("status")).toContainText("Assignment rule disabled")
  expect(updateRequests).toBe(1)
  await page.getByRole("button", { name: "Preview matches" }).click()
  await expect(page.getByText("No matching models found")).toBeVisible()
  page.once("dialog", dialog => dialog.accept())
  await page.getByRole("button", { name: "Delete", exact: true }).click()
  await expect(page.getByRole("article")).toBeVisible()
})
