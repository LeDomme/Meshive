import { expect, test, type Page } from "@playwright/test"

async function openLogin(page: Page) {
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({ json: null }))
  await page.route("**/api/auth/password-recovery/status", route => route.fulfill({ json: { enabled: false } }))
  await page.goto("/login")
}

test("particle network stays behind the interactive application", async ({ page }) => {
  await openLogin(page)

  const background = page.getByTestId("particle-network-background")
  await expect(background).toHaveAttribute("aria-hidden", "true")
  await expect(background).toHaveCSS("pointer-events", "none")
  await expect(background).toHaveCSS("position", "fixed")
  await expect(background).toHaveAttribute("data-motion-state", "active")

  await page.getByLabel("Username").fill("still interactive")
  await expect(page.getByLabel("Username")).toHaveValue("still interactive")
})

test("particle network disables animation for reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await openLogin(page)

  const background = page.getByTestId("particle-network-background")
  await expect(background).toHaveAttribute("data-motion-state", "reduced")
  await expect(background).toBeHidden()
})

test("disabled preference does not render or start the particle network", async ({ page }) => {
  await page.addInitScript(() => {
    const originalRequestAnimationFrame = window.requestAnimationFrame.bind(window)
    let animationFrameRequests = 0
    window.requestAnimationFrame = (callback: FrameRequestCallback) => {
      if (callback.name === "animate") animationFrameRequests += 1
      return originalRequestAnimationFrame(callback)
    }
    Object.defineProperty(window, "particleAnimationFrameRequests", {
      get: () => animationFrameRequests,
    })
  })
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/auth/me", route => route.fulfill({
    json: {
      id: 1,
      username: "Curator",
      email: null,
      email_verified: false,
      role: "user",
      is_active: true,
      must_change_password: false,
      animated_background: false,
      role_definition: null,
      permissions: ["catalogue.view"],
      source_access: { all_sources: true, source_ids: [] },
    },
  }))
  await page.route("**/api/auth/sessions", route => route.fulfill({ json: [] }))
  await page.route("**/api/auth/catalogue-preferences", route => route.fulfill({
    json: { filter_order: [], action_order: [], navigation_mode: "pagination", animated_background: false },
  }))
  await page.route("**/api/saved-views**", route => route.fulfill({ json: [] }))

  await page.goto("/account")

  await expect(page.getByTestId("particle-network-background")).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => (window as Window & { particleAnimationFrameRequests: number }).particleAnimationFrameRequests)).toBe(0)
})
