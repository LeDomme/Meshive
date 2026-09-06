import { expect, test } from "@playwright/test"

const user = {
  id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true,
  must_change_password: false, permissions: ["catalogue.view", "archives.view_entries"],
  source_access: { all_sources: true, source_ids: [] },
}
const model = {
  id: 1, name: "Browse model", variant: null, creator: null, creator_links: [], franchise: null,
  series: null, collection: null, status: "available", source_id: 1, source_name: "Library",
  relative_path: "Browse", images: [], archive_bundle_download_url: null, recent_scan_issues: [],
  archive_statistics: null, tags: [], archives: [{ id: 8, filename: "browse.7z", format: "7z", size_bytes: 42,
    status: "available", entry_count: 4, uncompressed_size_bytes: 42, error_message: null,
    download_url: "/api/models/1/archives/8/download", entries_url: "/api/models/1/archives/8/entries" }],
}

test("browses lazy archive folders and returns from a server search result", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
  await page.route("**/api/models/1/archives/8/entries**", route => {
    const query = new URL(route.request().url()).searchParams
    const search = query.get("search")
    const parent = query.get("parent_path")
    if (search) return route.fulfill({ json: { parent_path: null, next_cursor: null, items: [
      { path: "deep/nested/model.stl", name: "model.stl", is_directory: false, size_bytes: 2, compressed_size_bytes: 1, modified_at: null },
    ] } })
    if (parent === "deep") return route.fulfill({ json: { parent_path: "deep", next_cursor: null, items: [
      { path: "deep/nested", name: "nested", is_directory: true, size_bytes: null, compressed_size_bytes: null, modified_at: null },
    ] } })
    if (parent === "deep/nested") return route.fulfill({ json: { parent_path: "deep/nested", next_cursor: null, items: [
      { path: "deep/nested/model.stl", name: "model.stl", is_directory: false, size_bytes: 2, compressed_size_bytes: 1, modified_at: null },
    ] } })
    return route.fulfill({ json: { parent_path: "", next_cursor: null, items: [
      { path: "deep", name: "deep", is_directory: true, size_bytes: null, compressed_size_bytes: null, modified_at: null },
      { path: "readme.txt", name: "readme.txt", is_directory: false, size_bytes: 1, compressed_size_bytes: 1, modified_at: null },
    ] } })
  })

  await page.goto("/models/1")
  await expect(page.getByText("deep", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: /deep/ }).click()
  await expect(page.getByText("nested", { exact: true })).toBeVisible()
  await page.getByPlaceholder("Search archive contents…").fill("model")
  await expect(page.getByText("deep/nested/model.stl", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: /deep\/nested\/model.stl/ }).click()
  await expect(page.getByText("model.stl", { exact: true })).toBeVisible()
})

test("archive switches retry aborted roots without leaking another archive's state", async ({ page }) => {
  const requests: number[] = []
  const twoArchives = { ...model, archives: [
    { ...model.archives[0], id: 8, filename: "first.7z", entries_url: "/api/models/1/archives/8/entries" },
    { ...model.archives[0], id: 9, filename: "second.7z", entries_url: "/api/models/1/archives/9/entries" },
  ] }
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: twoArchives }))
  await page.route(/\/api\/models\/1\/archives\/(8|9)\/entries.*/, async route => {
    const archiveId = Number(route.request().url().match(/archives\/(\d+)/)?.[1])
    requests.push(archiveId)
    await route.fulfill({ json: { parent_path: "", next_cursor: null, items: [{
      path: `archive-${archiveId}.stl`, name: `archive-${archiveId}.stl`, is_directory: false,
      size_bytes: 1, compressed_size_bytes: 1, modified_at: null,
    }] } })
  })
  await page.goto("/models/1")
  await expect.poll(() => requests).toContain(8)
  await page.getByRole("button", { name: "second.7z" }).click()
  await expect.poll(() => requests).toContain(9)
  await expect(page.getByText("archive-9.stl", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "first.7z" }).click()
  await expect(page.getByText("archive-8.stl", { exact: true })).toBeVisible()
  expect(requests.filter(id => id === 8)).toHaveLength(1)
})
