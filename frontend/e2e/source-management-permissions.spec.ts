import { expect, test } from "@playwright/test"

const source = {
  id: 1,
  name: "Source A",
  root_path: "/models/source-a",
  directory_pattern: "{creator}/{model}",
  model_pattern: "{model}",
  archive_formats: ["7z", "zip"],
  image_formats: ["jpg", "png"],
  is_active: true,
  scan_enabled: true,
  auto_scan_enabled: false,
  auto_scan_frequency: "daily",
  auto_scan_time: "02:00",
  auto_scan_weekday: 0,
  auto_scan_timezone: "Europe/Berlin",
}

function user(permissions: string[], allSources = false) {
  return {
    id: 1,
    username: "Source manager",
    email: null,
    email_verified: false,
    role: "user",
    is_active: true,
    must_change_password: false,
    permissions,
    source_access: { all_sources: allSources, source_ids: allSources ? [] : [source.id] },
  }
}

async function mockSources(
  page: import("@playwright/test").Page,
  permissions: string[],
  allSources = false,
) {
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({ json: { required: false, enabled: false } }),
  )
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: user(permissions, allSources) }),
  )
  await page.route(/\/api\/admin\/library-sources$/, (route) =>
    route.fulfill({ json: [source] }),
  )
}

test("a scoped source manager edits only safe fields without scan requests", async ({ page }) => {
  const scanRequests: string[] = []
  let savedPayload: Record<string, unknown> | undefined
  await mockSources(page, ["sources.manage"])
  await page.route(/\/api\/admin\/(?:scans\/queue|library-sources\/1\/scans|scans\/\d+)$/, (route) => {
    scanRequests.push(route.request().url())
    return route.fulfill({ status: 403, json: { detail: "Permission denied" } })
  })
  await page.route(/\/api\/admin\/library-sources\/1$/, async (route) => {
    savedPayload = route.request().postDataJSON()
    await route.fulfill({ json: { ...source, name: savedPayload.name } })
  })

  await page.goto("/admin/sources")
  await expect(page.getByRole("heading", { name: "Configured sources" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Add source" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Preview values" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Delete" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Start scan" })).toHaveCount(0)

  await page.getByRole("button", { name: "Edit" }).click()
  await expect(page.getByText("This account can edit the source name and automatic scan schedule only.")).toBeVisible()
  await expect(page.getByLabel("Container path")).toHaveAttribute("readonly", "")
  await expect(page.getByLabel("Directory patterns")).toHaveAttribute("readonly", "")
  await expect(page.getByLabel("Model-name patterns")).toHaveAttribute("readonly", "")
  await expect(page.getByLabel("Active")).toBeDisabled()
  await expect(page.getByLabel("Scanning enabled")).toBeDisabled()
  await expect(page.getByText("Archive formats")).toBeVisible()
  await expect(page.getByText("7z, zip")).toBeVisible()

  await page.getByLabel("Name", { exact: true }).fill("Renamed source")
  await page.getByRole("button", { name: "Save changes" }).click()
  await expect.poll(() => savedPayload?.name).toBe("Renamed source")
  expect(scanRequests).toEqual([])

  await page.waitForTimeout(3_200)
  expect(scanRequests).toEqual([])
})

test("a full source manager retains full source controls", async ({ page }) => {
  await mockSources(page, ["sources.manage"], true)
  await page.route("**/api/admin/scans/queue", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/admin/library-sources/1/scans", (route) => route.fulfill({ json: [] }))

  await page.goto("/admin/sources")
  await expect(page.getByRole("heading", { name: "Add source" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Preview values" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Delete" })).toBeVisible()
  await expect(page.getByLabel("Container path")).not.toHaveAttribute("readonly", "")
  await expect(page.getByLabel("Active")).toBeEnabled()
  await expect(page.getByLabel("Scanning enabled")).toBeEnabled()
})

test("source scan controls follow their individual permissions", async ({ page }) => {
  const unexpectedRequests: string[] = []
  await mockSources(page, ["sources.manage", "scans.start"])
  await page.route(/\/api\/admin\/(?:scans\/queue|library-sources\/1\/scans|scans\/\d+)$/, (route) => {
    unexpectedRequests.push(route.request().url())
    return route.fulfill({ json: [] })
  })
  await page.route("**/api/admin/library-sources/1/scan", (route) =>
    route.fulfill({ json: { id: 2, library_source_id: 1, status: "pending" } }),
  )

  await page.goto("/admin/sources")
  await expect(page.getByLabel("Scan mode")).toBeVisible()
  await expect(page.getByRole("button", { name: "Scan now" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Scan activity" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Pause" })).toHaveCount(0)
  await page.getByRole("button", { name: "Scan now" }).click()
  await page.waitForTimeout(1_200)
  expect(unexpectedRequests).toEqual([])
})

test("view-only source scan UI loads activity but not start or control actions", async ({ page }) => {
  await mockSources(page, ["sources.manage", "scans.view"])
  await page.route("**/api/admin/scans/queue", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/admin/library-sources/1/scans", (route) => route.fulfill({ json: [] }))

  await page.goto("/admin/sources")
  await expect(page.getByRole("heading", { name: "Scan activity" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Scan now" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Pause" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0)
})

test("control-only source managers do not request view-only queue or history APIs", async ({ page }) => {
  const scanRequests: string[] = []
  await mockSources(page, ["sources.manage", "scans.control"])
  await page.route(/\/api\/admin\/(?:scans\/queue|library-sources\/1\/scans|scans\/\d+)$/, (route) => {
    scanRequests.push(route.request().url())
    return route.fulfill({ status: 403, json: { detail: "Permission denied" } })
  })

  await page.goto("/admin/sources")
  await expect(page.getByRole("heading", { name: "Scan activity" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Pause" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Resume" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0)
  await page.waitForTimeout(3_200)
  expect(scanRequests).toEqual([])
})
