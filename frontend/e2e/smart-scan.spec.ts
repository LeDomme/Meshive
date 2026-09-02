import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const source = { id: 1, name: "Test library", root_path: "/models", directory_pattern: "{model}", model_pattern: "{model}", archive_formats: ["7z"], image_formats: ["jpg"], is_active: true, scan_enabled: true, auto_scan_enabled: false, auto_scan_frequency: "daily", auto_scan_time: "02:00", auto_scan_weekday: 0, auto_scan_timezone: "Europe/Berlin" }

test("Smart Scan is the default and Incremental remains selectable", async ({ page }) => {
  const startedModes: string[] = []
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [source] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/library-sources/1/scans**", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/scans/2", route => route.fulfill({ json: { id: 2, library_source_id: 1, status: "completed", mode: "smart", trigger: "manual", created_at: "2026-01-01T00:00:00Z", models_found: 0, models_added: 0, models_updated: 0, models_missing: 0, models_skipped: 0, archive_images_reused: 0, archive_images_generated: 0, archive_images_removed: 0, automatic_tag_matches: 0, automatic_tags_added: 0, automatic_tags_removed: 0, issues_count: 0, error_message: null } }))
  await page.route("**/api/admin/library-sources/1/scan", async route => {
    const body = route.request().postDataJSON()
    startedModes.push(body.mode)
    expect(body).toEqual({ mode: startedModes.length === 1 ? "smart" : "incremental" })
    await route.fulfill({ json: { id: 2, library_source_id: 1, status: "completed", mode: body.mode, trigger: "manual", created_at: "2026-01-01T00:00:00Z", models_found: 0, models_added: 0, models_updated: 0, models_missing: 0, models_skipped: 0, archive_images_reused: 0, archive_images_generated: 0, archive_images_removed: 0, automatic_tag_matches: 0, automatic_tags_added: 0, automatic_tags_removed: 0, issues_count: 0, error_message: null } })
  })

  await page.goto("/admin/sources")
  await expect(page.getByLabel("Scan mode")).toHaveValue("smart")
  await page.getByRole("button", { name: "Scan now" }).click()
  await expect.poll(() => startedModes).toEqual(["smart"])

  await page.getByLabel("Scan mode").selectOption("incremental")
  await expect(page.getByLabel("Scan mode")).toHaveValue("incremental")
  await page.getByRole("button", { name: "Scan now" }).click()
  await expect.poll(() => startedModes).toEqual(["smart", "incremental"])
})

test("a finalizing scan does not display a stale model name", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [source] }))
  await page.route("**/api/admin/library-sources/1/scans**", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [{
    id: 2, library_source_id: 1, source_name: source.name, status: "running", mode: "smart", trigger: "manual",
    target_model_id: null, target_model_name: null, position: null, created_at: "2026-01-01T00:00:00Z", started_at: "2026-01-01T00:00:00Z",
    cancel_requested: false, pause_requested: false, current_phase: "finalizing", current_model_name: "Stale model", models_total: 2, models_found: 2, models_skipped: 0,
  }] }))

  await page.goto("/admin/sources")
  await expect(page.getByText("Finalizing scan")).toBeVisible()
  await expect(page.getByText("Stale model")).toHaveCount(0)
})

test("an explicit scan mode survives a configured-source reload", async ({ page }) => {
  const modes: string[] = []
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [source] }))
  await page.route("**/api/admin/library-sources/1/scans**", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/library-sources/1", route => route.fulfill({ json: source }))
  await page.route("**/api/admin/library-sources/1/scan", async route => {
    modes.push(route.request().postDataJSON().mode)
    await route.fulfill({ json: { id: 2, library_source_id: 1, status: "completed", mode: "incremental", trigger: "manual", created_at: "2026-01-01T00:00:00Z", models_found: 0, models_added: 0, models_updated: 0, models_missing: 0, models_skipped: 0, archive_images_reused: 0, archive_images_generated: 0, archive_images_removed: 0, automatic_tag_matches: 0, automatic_tags_added: 0, automatic_tags_removed: 0, issues_count: 0, error_message: null } })
  })
  await page.goto("/admin/sources")
  await page.getByLabel("Scan mode").selectOption("incremental")
  await page.getByRole("button", { name: "Edit" }).click()
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect(page.getByLabel("Scan mode")).toHaveValue("incremental")
  await page.getByRole("button", { name: "Scan now" }).click()
  await expect.poll(() => modes).toEqual(["incremental"])
})

test("running scans can be paused, resumed, and cancelled", async ({ page }) => {
  let paused = false
  let cancelled = false
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route(/\/api\/setup\/status/, route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/admin/library-sources", route => route.fulfill({ json: [source] }))
  await page.route("**/api/admin/library-sources/1/scans**", route => route.fulfill({ json: [] }))
  await page.route("**/api/admin/scans/queue", route => route.fulfill({ json: cancelled ? [] : [{
    id: 2, library_source_id: 1, source_name: source.name, status: "running", mode: "smart", trigger: "manual",
    target_model_id: null, target_model_name: null, position: null, created_at: "2026-01-01T00:00:00Z", started_at: "2026-01-01T00:00:00Z",
    cancel_requested: false, pause_requested: paused, current_phase: "scanning", current_model_name: "Model", models_total: 2, models_found: 1, models_skipped: 0,
  }] }))
  await page.route("**/api/admin/scans/2/pause", async route => { expect(route.request().method()).toBe("POST"); paused = true; await route.fulfill({ json: {} }) })
  await page.route("**/api/admin/scans/2/resume", async route => { expect(route.request().method()).toBe("POST"); paused = false; await route.fulfill({ json: {} }) })
  await page.route("**/api/admin/scans/2/cancel", async route => { expect(route.request().method()).toBe("POST"); cancelled = true; await route.fulfill({ json: {} }) })

  await page.goto("/admin/sources")
  await page.getByRole("button", { name: "Pause" }).click()
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible()
  await page.getByRole("button", { name: "Resume" }).click()
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible()
  await page.getByRole("button", { name: "Cancel" }).click()
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0)
})
