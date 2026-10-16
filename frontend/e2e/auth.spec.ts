import { expect, test } from "@playwright/test"

const admin = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false, permissions: ["catalogue.view", "diagnostics.view"], source_access: { all_sources: true, source_ids: [] } }
const user = { ...admin, id: 2, username: "User", role: "user", permissions: [] }
const emptyFilters = { models: [], creators: [], franchises: [], series: [], collections: [], sources: [], statuses: [], tags: [] }

test("login submits credentials and opens the catalogue", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: null }))
  await page.route("**/api/auth/password-recovery/status", route => route.fulfill({ json: { enabled: false } }))
  await page.route("**/api/auth/login", async route => {
    expect(route.request().postDataJSON()).toEqual({ username: "admin", password: "secret" })
    await route.fulfill({ json: admin })
  })
  await page.route("**/api/models/filters**", route => route.fulfill({ json: emptyFilters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 24 } }))

  await page.goto("/login")
  await page.getByLabel("Username").fill("admin")
  await page.getByLabel("Password").fill("secret")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/(?:\?.*)?$/)
})

test("regular users are redirected away from administration", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/models/filters**", route => route.fulfill({ json: emptyFilters }))
  await page.route("**/api/models?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 24 } }))

  await page.goto("/admin/diagnostics")
  await expect(page).toHaveURL(/\/access-denied$/)
  await expect(page.getByRole("link", { name: "Diagnostics" })).toHaveCount(0)
})

test("administrators can open diagnostics from administration navigation", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ json: [] }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: admin }))
  await page.route("**/api/admin/diagnostics", route => route.fulfill({ json: {
    application: { version: "1.5.2", environment: "test" }, database: { backend: "sqlite", reachable: true }, storage: {},
    archive_backend: { command: "7z", available: true }, scanner: { max_concurrent_scans: 1, running: 0, pending: 0 },
    scheduler: { thread_alive: true, last_check_at: null, last_success_at: null, last_error_at: null, last_error: null }, catalogue: {},
  } }))

  await page.goto("/admin/diagnostics")
  await page.locator(".account-menu summary").click()
  await expect(page.getByRole("link", { name: "Diagnostics" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Diagnostics", level: 1 })).toBeVisible()
})

test("account settings use the assigned custom role and account navigation", async ({ page }) => {
  const customRoleUser = {
    ...user,
    username: "Rule manager",
    role_definition: { id: 7, name: "Library curator", is_system: false, is_superuser: false },
  }
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: customRoleUser }))
  await page.route("**/api/auth/sessions", route => route.fulfill({ json: [] }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [], action_order: [], navigation_mode: "pagination" } }))
  await page.route("**/api/saved-views", route => route.fulfill({ json: [] }))

  await page.goto("/account")

  await expect(page.getByRole("heading", { name: "Account settings", level: 1 })).toBeVisible()
  await expect(page.getByLabel("Profile").getByText("Library curator", { exact: true })).toBeVisible()
  await expect(page.getByText("Your Meshive account", { exact: true })).toBeVisible()
  await expect(page.locator(".account-menu")).toBeVisible()
  await expect(page.getByRole("region", { name: "Temporary Catalogue Links" })).toHaveCount(0)
})

test("permitted users can create a short-lived API token from account settings", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "__apiTokenCopied", { configurable: true, value: "", writable: true })
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          window.__apiTokenCopied = value
        },
      },
    })
  })
  const tokenUser = {
    ...user,
    permissions: ["api_tokens.manage_own"],
    role_definition: { id: 8, name: "API Reader", is_system: false, is_superuser: false },
  }
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: tokenUser }))
  await page.route("**/api/auth/sessions", route => route.fulfill({ json: [] }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [], action_order: [], navigation_mode: "pagination", animated_background: true } }))
  await page.route("**/api/saved-views", route => route.fulfill({ json: [] }))
  await page.route("**/api/account/tokens", async route => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toEqual({
        name: "Temporary reader",
        expires_in_seconds: 900,
        current_password: "secret",
      })
      await route.fulfill({
        status: 201,
        json: {
          id: 1,
          name: "Temporary reader",
          token_prefix: "msh_pat_example...",
          token: "msh_pat_example-secret",
          created_at: "2026-10-16T12:00:00Z",
          expires_at: "2026-10-16T12:15:00Z",
          last_used_at: null,
          status: "active",
        },
      })
      return
    }
    await route.fulfill({ json: [] })
  })

  await page.goto("/account")
  const section = page.getByRole("region", { name: "API Tokens" })
  await expect(section).toBeVisible()
  await expect(section.getByLabel("Expiration")).toHaveCSS("background-color", "rgb(11, 18, 32)")
  await expect(section.getByLabel("Expiration")).toHaveCSS("border-top-color", "rgb(51, 65, 85)")
  await section.getByLabel("Name").fill("Temporary reader")
  await section.getByLabel("Expiration").selectOption("custom")
  await expect(section.getByLabel("Unit")).toHaveCSS("background-color", "rgb(11, 18, 32)")
  await expect(section.getByLabel("Unit")).toHaveCSS("border-top-color", "rgb(51, 65, 85)")
  await section.getByLabel("Expiration").selectOption("900")
  await section.getByLabel("Current password").fill("secret")
  await section.getByRole("button", { name: "Create token" }).click()
  await expect(section.getByText("msh_pat_example-secret", { exact: true })).toBeVisible()
  await expect(section.getByText("Copy this token now. Meshive will not show it again.")).toBeVisible()
  await section.getByRole("button", { name: "Copy" }).click()
  await expect(section.getByText("Copied.", { exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__apiTokenCopied)).toBe("msh_pat_example-secret")
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => { throw new Error("Clipboard unavailable") } },
    })
    window.__apiTokenFallbackCount = 0
    document.execCommand = (command: string) => {
      if (command === "copy") window.__apiTokenFallbackCount += 1
      return command === "copy"
    }
  })
  await section.getByRole("button", { name: "Copy" }).click()
  await expect.poll(() => page.evaluate(() => window.__apiTokenFallbackCount)).toBe(1)
  await section.getByRole("button", { name: "Done" }).click()
  await expect(section.getByText("msh_pat_example-secret", { exact: true })).toHaveCount(0)
})

test("temporary catalogue links are permission-controlled and shown only once", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "__shareLinkCopied", { configurable: true, value: "", writable: true })
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (value: string) => { window.__shareLinkCopied = value } },
    })
  })
  const shareUser = {
    ...user,
    permissions: ["catalogue_share_links.manage_own"],
    role_definition: { id: 9, name: "Share reader", is_system: false, is_superuser: false },
  }
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: shareUser }))
  await page.route("**/api/auth/sessions", route => route.fulfill({ json: [] }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({ json: { filter_order: [], action_order: [], navigation_mode: "pagination", animated_background: true } }))
  await page.route("**/api/saved-views", route => route.fulfill({ json: [] }))
  let revoked = false
  await page.route("**/api/account/catalogue-share-links**", async route => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toEqual({ name: "ChatGPT check", expires_in_seconds: 900, current_password: "secret" })
      await route.fulfill({ status: 201, json: { id: 1, name: "ChatGPT check", token_prefix: "msh_share_example...", token: "msh_share_example-secret", created_at: "2026-10-16T12:00:00Z", expires_at: "2026-10-16T12:15:00Z", last_used_at: null, status: "active" } })
      return
    }
    if (route.request().method() === "DELETE") {
      expect(route.request().url()).toContain("/api/account/catalogue-share-links/2")
      revoked = true
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({
      json: revoked
        ? []
        : [{ id: 2, name: "Existing link", token_prefix: "msh_share_existing...", created_at: "2026-10-16T12:00:00Z", expires_at: "2026-10-16T12:15:00Z", last_used_at: null, status: "active" }],
    })
  })
  await page.goto("/account")
  const section = page.getByRole("region", { name: "Temporary Catalogue Links" })
  await expect(section).toBeVisible()
  await expect(section.getByLabel("Expiration")).toHaveText(/5 minutes.*15 minutes.*30 minutes.*60 minutes/s)
  await section.getByLabel("Name").fill("ChatGPT check")
  await section.getByLabel("Current password").fill("secret")
  await section.getByRole("button", { name: "Create link" }).click()
  const url = "http://127.0.0.1:5173/api/share/catalogue/msh_share_example-secret/models"
  await expect(section.getByText(url, { exact: true })).toBeVisible()
  await section.getByRole("button", { name: "Copy" }).click()
  await expect(section.getByText("Copied.", { exact: true })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__shareLinkCopied)).toBe(url)
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => { throw new Error("Clipboard unavailable") } } })
    window.__shareLinkFallbackCount = 0
    document.execCommand = (command: string) => { if (command === "copy") window.__shareLinkFallbackCount += 1; return command === "copy" }
  })
  await section.getByRole("button", { name: "Copy" }).click()
  await expect.poll(() => page.evaluate(() => window.__shareLinkFallbackCount)).toBe(1)
  await section.getByRole("button", { name: "Done" }).click()
  await expect(section.getByText(url, { exact: true })).toHaveCount(0)
  await expect(section.getByText("msh_share_example-secret", { exact: true })).toHaveCount(0)
  await expect(section.getByText("Existing link", { exact: true })).toBeVisible()
  page.once("dialog", dialog => dialog.accept())
  await section.getByRole("button", { name: "Revoke" }).click()
  await expect(section.getByText("Existing link", { exact: true })).toHaveCount(0)
})
