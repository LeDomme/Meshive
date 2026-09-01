import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const source = { id: 1, name: "Test library", root_path: "/models", directory_pattern: "{model}", model_pattern: "{model}", archive_formats: ["7z"], image_formats: ["jpg"], is_active: true, scan_enabled: true, auto_scan_enabled: false, auto_scan_frequency: "daily", auto_scan_time: "02:00", auto_scan_weekday: 0, auto_scan_timezone: "Europe/Berlin" }

test("Smart Scan is selectable and starts with smart mode", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [source] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/library-sources/1/scans**", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/scans/2", route => route.fulfill({ json: { id: 2, library_source_id: 1, status: "completed", mode: "smart", trigger: "manual", created_at: "2026-01-01T00:00:00Z", models_found: 0, models_added: 0, models_updated: 0, models_missing: 0, models_skipped: 0, archive_images_reused: 0, archive_images_generated: 0, archive_images_removed: 0, automatic_tag_matches: 0, automatic_tags_added: 0, automatic_tags_removed: 0, issues_count: 0, error_message: null } }))
  await page.route("**/api/admin/library-sources/1/scan", async route => {
    expect(route.request().postDataJSON()).toEqual({ mode: "smart" })
    await route.fulfill({ json: { id: 2, library_source_id: 1, status: "pending", mode: "smart", trigger: "manual", created_at: "2026-01-01T00:00:00Z", models_found: 0, models_added: 0, models_updated: 0, models_missing: 0, models_skipped: 0, archive_images_reused: 0, archive_images_generated: 0, archive_images_removed: 0, automatic_tag_matches: 0, automatic_tags_added: 0, automatic_tags_removed: 0, issues_count: 0, error_message: null } })
  })

  await page.goto("/admin/sources")
  await page.getByLabel("Scan mode").selectOption("smart")
  await expect(page.getByLabel("Scan mode")).toHaveValue("smart")
  await page.getByRole("button", { name: "Scan now" }).click()
})
