import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false, permissions: ["catalogue.view", "archives.download", "archives.view_entries"], source_access: { all_sources: true, source_ids: [] } }
const model = { id: 1, name: "Download model", variant: null, creator: null, creator_links: [], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: "Download", images: [], archives: [{ id: 8, filename: "model.7z", format: "7z", size_bytes: 42, status: "available", entry_count: 0, uncompressed_size_bytes: 42, error_message: null, download_url: "/api/archives/8/download", entries_url: "/api/models/1/archives/8/entries" }], archive_bundle_download_url: "/api/models/1/download-bundle", recent_scan_issues: [], archive_statistics: null, tags: [] }

test("archive download link targets the selected protected archive", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1/archives/8/entries**", route => route.fulfill({ json: { items: [], next_cursor: null, parent_path: "" } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
  await page.goto("/models/1")
  const archive = page.getByRole("link", { name: "Download archive" })
  await expect(archive).toHaveAttribute("href", "/api/archives/8/download")
  await expect(archive).toHaveAttribute("download", "model.7z")
  await expect(page.getByRole("link", { name: "Download all archives" })).toHaveAttribute("href", "/api/models/1/download-bundle")
})

test("archive permissions hide downloads and explain unavailable contents", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: { ...user, permissions: ["catalogue.view"] } }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1/archives/8/entries**", route => route.fulfill({ json: { items: [], next_cursor: null, parent_path: "" } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
  await page.goto("/models/1")

  await expect(page.getByRole("link", { name: "Download archive" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Download all archives" })).toHaveCount(0)
  await expect(page.getByText("Archive contents are not available for your role.")).toBeVisible()
})
