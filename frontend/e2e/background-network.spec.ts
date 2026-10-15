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
