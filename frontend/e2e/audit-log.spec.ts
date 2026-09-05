import { expect, test } from "@playwright/test"

function user(permissions: string[], allSources = true) { return { id: 1, username: "Admin", email: null, email_verified: false, role: "user", is_active: true, must_change_password: false, permissions, source_access: { all_sources: allSources, source_ids: [] } } }
async function auth(page: import("@playwright/test").Page, permissions: string[], allSources = true) { await page.route("**/api/setup/status", r => r.fulfill({ json: { required: false, enabled: false } })); await page.route("**/api/auth/me", r => r.fulfill({ json: user(permissions, allSources) })) }
test("audit log is permission gated, readable, filterable and paginated", async ({ page }) => {
  await auth(page, ["audit.view"])
  const requests: string[] = []
  await page.route("**/api/admin/audit-events**", route => { requests.push(route.request().url()); const pageNo = new URL(route.request().url()).searchParams.get("page"); return route.fulfill({ json: { total: 2, items: pageNo === "2" ? [{ id: 1, created_at: "2026-01-01T00:00:00Z", actor_username: "Alice", action: "user.updated", target_type: "user", target_label: "Bob" }] : [{ id: 2, created_at: "2026-01-02T00:00:00Z", actor_username: "Alice", action: "role.updated", target_type: "role", target_label: "Curator" }] } }) })
  await page.goto("/admin/audit")
  await expect(page.locator(".audit-row").getByText("Role updated")).toBeVisible()
  await expect(page.getByText("role.updated", { exact: true })).toHaveCount(0)
  await page.getByLabel("Action").selectOption("role.updated"); await page.getByLabel("Actor").fill("Alice"); await page.getByLabel("From", { exact: true }).fill("2026-01-01T00:00"); await page.getByLabel("To", { exact: true }).fill("2026-01-03T00:00"); await page.getByRole("button", { name: "Apply filters" }).click()
  await page.getByRole("button", { name: "Load more" }).click()
  await expect(page.locator(".audit-row").getByText("User updated")).toBeVisible(); expect(requests.some(url => url.includes("from_at=") && url.includes("to_at="))).toBe(true); expect(new Set(requests).size).toBeGreaterThan(1)
  await page.locator(".account-menu summary").click(); await expect(page.getByRole("link", { name: "Audit log" })).toBeVisible()
})
test("audit link and route require audit view plus all sources", async ({ page }) => {
  await auth(page, [])
  await page.goto("/admin/audit"); await expect(page).not.toHaveURL(/\/admin\/audit/); await expect(page.getByRole("link", { name: "Audit log" })).toHaveCount(0)
  await auth(page, ["audit.view"], false)
  await page.goto("/admin/audit"); await expect(page).not.toHaveURL(/\/admin\/audit/)
})

test("audit log renders source and scan actions with readable labels", async ({ page }) => {
  await auth(page, ["audit.view"])
  await page.route("**/api/admin/audit-events**", route => route.fulfill({ json: { total: 2, items: [
    { id: 2, created_at: "2026-01-02T00:00:00Z", actor_username: "Alice", action: "scan.pause_requested", target_type: "scan", target_label: "Smart scan for Library" },
    { id: 1, created_at: "2026-01-01T00:00:00Z", actor_username: "Alice", action: "source.updated", target_type: "library_source", target_label: "Library" },
  ] } }))
  await page.goto("/admin/audit")
  await expect(page.locator(".audit-row").getByText("Source updated", { exact: true })).toBeVisible()
  await expect(page.locator(".audit-row").getByText("Scan pause requested", { exact: true })).toBeVisible()
  await expect(page.getByText("source.updated", { exact: true })).toHaveCount(0)
  await expect(page.getByText("scan.pause_requested", { exact: true })).toHaveCount(0)
})
