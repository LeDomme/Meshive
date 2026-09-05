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

test("tag-rule managers see only their rule types", async ({ page }) => {
  let folderRequest = false
  await mockAuth(page, ["tag_rules.manage"])
  await page.route("**/api/admin/tags/library-sources", route => { folderRequest = true; return route.fulfill({ status: 403 }) })
  await page.route("**/api/admin/folder-tag-rules", route => { folderRequest = true; return route.fulfill({ status: 403 }) })
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [{ id: 1, name: "Bust", color: null, description: null }] }))
  await page.route("**/api/admin/automatic-tag-rules", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/folder-name-tag-rules", route => route.fulfill({ json: [] }))

  await page.goto("/admin/tags")
  await expect(page.getByRole("heading", { name: "Tag rules" })).toBeVisible()
  await expect(page.getByLabel("Rule type").locator('option[value="archive_entry_text"]')).toHaveCount(1)
  await expect(page.getByLabel("Rule type").locator('option[value="folder_name_regex"]')).toHaveCount(1)
  await expect(page.getByLabel("Rule type").locator('option[value="folder_path"]')).toHaveCount(0)
  await expect(page.locator(".admin-grid > .panel").filter({ has: page.getByRole("heading", { name: "Tags", exact: true }) })).toHaveCount(0)
  expect(folderRequest).toBe(false)
})

test("tag managers load tag and folder administration but no automatic rules", async ({ page }) => {
  let automaticRequest = false
  let folderNameRequest = false
  await mockAuth(page, ["tags.manage"])
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/folder-tag-rules", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/automatic-tag-rules", route => { automaticRequest = true; return route.fulfill({ status: 403 }) })
  await page.route("**/api/admin/folder-name-tag-rules**", route => { folderNameRequest = true; return route.fulfill({ status: 403 }) })

  await page.goto("/admin/tags")
  await expect(page.locator(".admin-grid > .panel").filter({ has: page.getByRole("heading", { name: "Tags", exact: true }) })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Tag rules" })).toBeVisible()
  await expect(page.getByLabel("Rule type").locator('option[value="folder_path"]')).toHaveCount(1)
  await expect(page.getByLabel("Rule type").locator('option[value="archive_entry_text"]')).toHaveCount(0)
  await expect(page.getByLabel("Rule type").locator('option[value="folder_name_regex"]')).toHaveCount(0)
  expect(automaticRequest).toBe(false)
  expect(folderNameRequest).toBe(false)
})

test("folder-name rule preview is available only to tag-rule managers and does not save", async ({ page }) => {
  await mockAuth(page, ["tag_rules.manage"])
  let previewRequested = false
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [{ id: 1, name: "Variant", color: null, description: null }] }))
  await page.route("**/api/admin/automatic-tag-rules", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/folder-name-tag-rules", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/folder-name-tag-rules/preview", route => {
    previewRequested = true
    return route.fulfill({ json: [{ model_name: "P1", relative_path: "Sets/psup_p1/Model" }] })
  })

  await page.goto("/admin/tags")
  const section = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Tag rules" }) })
  await section.getByLabel("Rule type").selectOption("folder_name_regex")
  await section.getByRole("textbox", { name: "Folder name regex" }).fill("_p[12]$")
  await section.getByRole("button", { name: "Preview" }).click()
  await expect(section.getByText("P1 · Sets/psup_p1/Model")).toBeVisible()
  expect(previewRequested).toBe(true)
})

test("tag rules share type-specific creation, editing, and deletion controls", async ({ page }) => {
  await mockAuth(page, ["tags.manage", "tag_rules.manage"])
  const calls: Array<{ url: string; method: string }> = []
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [{ id: 1, name: "Library" }] }))
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [{ id: 1, name: "Variant", color: null, description: null }] }))
  await page.route("**/api/admin/folder-tag-rules", route => {
    if (route.request().method() === "GET") return route.fulfill({ json: [{ id: 2, library_source_id: 1, relative_path: "Series", tag_id: 1, tag_name: "Variant", recursive: true }] })
    calls.push({ url: route.request().url(), method: route.request().method() })
    return route.fulfill({ status: 201, json: {} })
  })
  await page.route("**/api/admin/folder-tag-rules/*", route => { calls.push({ url: route.request().url(), method: route.request().method() }); return route.fulfill({ status: 204 }) })
  await page.route("**/api/admin/automatic-tag-rules", route => {
    if (route.request().method() === "GET") return route.fulfill({ json: [{ id: 4, tag_id: 1, tag_name: "Variant", pattern: "Bust", enabled: true, match_count: 2, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }] })
    calls.push({ url: route.request().url(), method: route.request().method() })
    return route.fulfill({ status: 204 })
  })
  await page.route("**/api/admin/folder-name-tag-rules", route => {
    if (route.request().method() === "GET") return route.fulfill({ json: [{ id: 3, tag_id: 1, tag_name: "Variant", pattern: "_p[12]$", enabled: true, match_count: 1 }] })
    calls.push({ url: route.request().url(), method: route.request().method() })
    return route.fulfill({ status: 201, json: {} })
  })
  await page.route("**/api/admin/folder-name-tag-rules/*", route => { calls.push({ url: route.request().url(), method: route.request().method() }); return route.fulfill({ status: 204 }) })
  await page.route("**/api/admin/folder-name-tag-rules/preview", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/automatic-tag-rules/*", route => { calls.push({ url: route.request().url(), method: route.request().method() }); return route.fulfill({ status: 204 }) })

  await page.goto("/admin/tags")
  const section = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Tag rules" }) })
  await section.getByLabel("Rule type").selectOption("folder_path")
  await expect(section.getByLabel("Source")).toBeVisible()
  await expect(section.getByLabel("Relative folder")).toBeVisible()
  await expect(section.getByRole("textbox", { name: "Folder name regex" })).toHaveCount(0)
  await section.getByLabel("Source").selectOption("1")
  await section.getByLabel("Relative folder").fill("Series")
  await section.getByLabel("Assign tag").first().selectOption("1")
  await section.getByRole("button", { name: "Add rule" }).click()
  await expect.poll(() => calls.some(call => call.url.includes("/folder-tag-rules") && call.method === "POST")).toBe(true)

  await section.getByLabel("Rule type").selectOption("folder_name_regex")
  await expect(section.getByRole("textbox", { name: "Folder name regex" })).toBeVisible()
  await section.getByRole("textbox", { name: "Folder name regex" }).fill("_p[12]$")
  await section.getByLabel("Assign tag").first().selectOption("1")
  await section.getByRole("button", { name: "Add rule" }).click()
  await expect.poll(() => calls.some(call => call.url.endsWith("/folder-name-tag-rules") && call.method === "POST")).toBe(true)

  await section.getByLabel("Rule type").selectOption("archive_entry_text")
  await expect(section.getByRole("textbox", { name: "Archive entry text" })).toBeVisible()
  await expect(section.getByLabel("Source")).toHaveCount(0)
  await section.getByRole("textbox", { name: "Archive entry text" }).fill("Bust")
  await section.getByLabel("Assign tag").first().selectOption("1")
  await section.getByRole("button", { name: "Add rule" }).click()
  await expect.poll(() => calls.some(call => call.url.endsWith("/automatic-tag-rules") && call.method === "POST")).toBe(true)

  const rows = section.getByRole("article")
  await rows.filter({ hasText: "Archive entry text" }).getByRole("button", { name: "Edit" }).click()
  const editor = rows.filter({ hasText: "Archive entry text" })
  await editor.getByRole("textbox", { name: "Archive entry text" }).fill("Mini")
  await editor.getByRole("button", { name: "Save" }).click()
  await expect.poll(() => calls.some(call => call.url.includes("/automatic-tag-rules/4") && call.method === "PUT")).toBe(true)
  page.on("dialog", dialog => dialog.accept())
  await rows.filter({ hasText: "Folder path" }).getByRole("button", { name: "Delete" }).click()
  await expect.poll(() => calls.some(call => call.url.includes("/folder-tag-rules/2") && call.method === "DELETE")).toBe(true)
  await rows.filter({ hasText: "Folder name regex" }).getByRole("button", { name: "Delete" }).click()
  await expect.poll(() => calls.some(call => call.url.includes("/folder-name-tag-rules/3") && call.method === "DELETE")).toBe(true)
  await rows.filter({ hasText: "Archive entry text" }).getByRole("button", { name: "Delete" }).click()
  await expect.poll(() => calls.some(call => call.url.includes("/automatic-tag-rules/4") && call.method === "DELETE")).toBe(true)
})

test("metadata and tag routes require their permissions and all-sources access", async ({ page }) => {
  await mockAuth(page, ["metadata.manage"], false)
  await page.goto("/admin/metadata")
  await expect(page).not.toHaveURL(/\/admin\/metadata/)
  await page.goto("/admin/tags")
  await expect(page).not.toHaveURL(/\/admin\/tags/)
})
