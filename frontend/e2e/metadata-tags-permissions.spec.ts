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

test("creator artwork previews and direct merge undo preserve the metadata document", async ({ page }) => {
  let merged = false
  let artworkUploads = 0
  const imageErrors: string[] = []
  page.on("console", message => {
    if (message.type() === "error") imageErrors.push(message.text())
  })
  let mergeHistory = [{ id: 9, source_display_name: "Source Creator", undone_at: null as string | null }]
  const profiles = () => [
    { id: 1, display_name: "Target Creator", normalized_name: "target creator", description: null, aliases: [] },
    ...(merged ? [] : [{ id: 2, display_name: "Source Creator", normalized_name: "source creator", description: null, aliases: [] }]),
  ]
  const metadata = () => [
    { entity_type: "creator", value: "Target Creator", model_count: 1, artwork_url: "/artwork/target.webp" },
    ...(merged ? [] : [{ entity_type: "creator", value: "Source Creator", model_count: 1, artwork_url: null }]),
  ]
  const creatorLinks = () => [
    { name: "Target Creator", model_count: 1, links: [] },
    ...(merged ? [] : [{ name: "Source Creator", model_count: 1, links: [] }]),
  ]

  await mockAuth(page, ["metadata.manage"])
  await page.route("**/api/admin/creator-links", route => route.fulfill({ json: creatorLinks() }))
  await page.route("**/api/admin/metadata", route => route.fulfill({ json: metadata() }))
  await page.route("**/api/admin/creator-profiles/1/merge-history", route => route.fulfill({ json: mergeHistory }))
  await page.route("**/api/admin/creator-profiles/2/merge-history", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/creator-profiles/1", route => route.fulfill({ json: profiles()[0] }))
  await page.route("**/api/admin/metadata/artwork", async route => {
    artworkUploads += 1
    await route.fulfill({ json: {
      id: 1,
      entity_type: "creator",
      value: "Target Creator",
      artwork_url: "/artwork/saved.webp",
      width: 1,
      height: 1,
    } })
  })
  await page.route("**/api/admin/creator-profiles/merges/9/undo", async route => {
    merged = false
    mergeHistory = [{ id: 9, source_display_name: "Source Creator", undone_at: "2026-01-01T00:00:00Z" }]
    await route.fulfill({ status: 204 })
  })
  await page.route("**/api/admin/creator-profiles/merge/preview", route => route.fulfill({ json: {
    favorite_count: 0, duplicate_favorite_count: 0, duplicate_link_ids: [], link_conflicts: [], artwork_conflict: false,
  } }))
  await page.route("**/api/admin/creator-profiles/merge", async route => {
    merged = true
    await route.fulfill({ status: 204 })
  })
  await page.route("**/api/admin/creator-profiles", route => route.fulfill({ json: profiles() }))

  await page.setViewportSize({ width: 1280, height: 400 })
  await page.goto("/admin/metadata")
  await page.getByRole("button", { name: "Creator", exact: true }).click()
  await page.getByRole("option", { name: "Target Creator" }).click()
  const artwork = page.locator(".metadata-artwork-preview img")
  const originalArtworkSrc = await artwork.getAttribute("src")
  expect(originalArtworkSrc).toContain("/artwork/target.webp")
  await page.getByLabel("Image file").setInputFiles({
    name: "preview.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLJ1wAAAABJRU5ErkJggg==", "base64"),
  })
  await expect(artwork).toHaveAttribute("src", /^blob:/)
  await expect(page.locator(".metadata-artwork-preview span")).toHaveText("Unsaved")
  await expect.poll(() => artwork.evaluate(image => image.naturalWidth)).toBeGreaterThan(0)
  await expect.poll(() => artwork.evaluate(image => image.naturalHeight)).toBeGreaterThan(0)
  expect(await artwork.getAttribute("src")).not.toBe(originalArtworkSrc)
  expect(artworkUploads).toBe(0)
  const saveChanges = page.locator(".creator-profile-section .row-actions .primary-button")
  await saveChanges.click()
  await expect(saveChanges).toHaveText("✓ Saved")
  await expect(page.locator(".success-panel")).toHaveCount(0)
  await expect(saveChanges).toHaveText("Save changes", { timeout: 3_000 })
  await expect(artwork).toHaveAttribute("src", /\/artwork\/saved\.webp$/)
  await expect(page.locator(".metadata-artwork-preview span")).toHaveText("Custom artwork")
  expect(imageErrors.filter(message => /content security policy|blob:|image/i.test(message))).toEqual([])
  await page.getByRole("button", { name: "Creator", exact: true }).click()
  await page.locator(".searchable-filter-options").getByText("Source Creator", { exact: true }).click()
  await expect(artwork).toHaveAttribute("src", /favorite-creator\.webp$/)
  await page.getByRole("button", { name: "Creator", exact: true }).click()
  await page.locator(".searchable-filter-options").getByText("Target Creator", { exact: true }).click()

  await page.evaluate(() => { (window as Window & { meshiveSentinel?: string }).meshiveSentinel = "kept" })
  await page.getByRole("button", { name: "Merge", exact: true }).scrollIntoViewIfNeeded()
  const scrollY = await page.evaluate(() => window.scrollY)
  expect(scrollY).toBeGreaterThan(0)
  await page.getByRole("combobox").last().selectOption("2")
  await page.getByRole("button", { name: "Merge", exact: true }).click()
  await expect(page.locator(".merged-creator")).toContainText("Source Creator")
  await expect(page.getByText("Apply merge", { exact: true })).toHaveCount(0)
  await expect(page.getByText("0 favorites; 0 duplicates; 0 duplicate links.", { exact: true })).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => (window as Window & { meshiveSentinel?: string }).meshiveSentinel)).toBe("kept")
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(scrollY - 100)
  await expect(page).toHaveURL(/\/admin\/metadata$/)

  await page.getByRole("button", { name: "Remove merge" }).click()
  await expect.poll(() => page.evaluate(() => (window as Window & { meshiveSentinel?: string }).meshiveSentinel)).toBe("kept")
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(scrollY - 100)
  await page.getByRole("button", { name: "Creator", exact: true }).click()
  await expect(page.locator(".searchable-filter-options").getByText("Source Creator", { exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Remove merge" })).toHaveCount(0)
  await expect(page).toHaveURL(/\/admin\/metadata$/)
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

test("TagsView colour picker and search targets are keyboard accessible", async ({ page }) => {
  await mockAuth(page, ["tags.manage", "tag_rules.manage"])
  await page.route("**/api/admin/tags/library-sources", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags/1/assignment-rules", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/tags", route => route.fulfill({ json: [{ id: 1, name: "Bust", color: "#5eead4", description: null }] }))
  await page.goto("/admin/tags")
  await page.getByRole("button", { name: "Create tag" }).click()
  await page.getByRole("button", { name: /#5EEAD4/i }).click()
  await page.getByLabel("HEX colour").fill("not-a-colour")
  await page.getByLabel("HEX colour").press("Enter")
  await expect(page.getByRole("alert")).toContainText("six-digit HEX")
  await page.getByLabel("HEX colour").fill("#38bdf8")
  await page.getByLabel("HEX colour").press("Enter")
  await expect(page.getByRole("button", { name: /#38BDF8/ })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByLabel("HEX colour")).toHaveCount(0)

  await page.getByRole("button", { name: "Cancel" }).click()
  await page.getByRole("checkbox", { name: "Model relative path" }).check()
  await expect(page.getByRole("checkbox", { name: "Model relative path" })).toBeChecked()
  await page.getByRole("checkbox", { name: "Model relative path" }).uncheck()
  await expect(page.getByRole("checkbox", { name: "Model relative path" })).not.toBeChecked()
})
