import { expect, test } from "@playwright/test"

const user = { id: 1, username: "Admin", email: null, email_verified: false, role: "admin", is_active: true, must_change_password: false }
const images = [1, 2, 3].map(id => ({ id, filename: `picture-${id}.jpg`, format: "jpg", size_bytes: 1, is_primary: id === 1, url: `/images/${id}.jpg` }))
const model = { id: 1, name: "Gallery model", variant: null, creator: null, creator_links: [], franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Library", relative_path: "Gallery", images, archives: [], archive_bundle_download_url: null, recent_scan_issues: [], archive_statistics: null, tags: [] }

test("gallery buttons and a horizontal swipe select exactly one adjacent image", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
  await page.goto("/models/1")
  const image = page.getByRole("img", { name: "Gallery model — picture-1.jpg" })
  await expect(image).toBeVisible()
  await page.getByRole("button", { name: "Next picture" }).click()
  await expect(page.getByRole("img", { name: "Gallery model — picture-2.jpg" })).toBeVisible()
  await page.getByRole("button", { name: "Previous picture" }).click()
  await expect(image).toBeVisible()
  const frame = page.locator(".detail-image-frame")
  await frame.dispatchEvent("pointerdown", { pointerId: 1, pointerType: "touch", clientX: 200, clientY: 100 })
  await frame.dispatchEvent("pointermove", { pointerId: 1, pointerType: "touch", clientX: 80, clientY: 100 })
  await frame.dispatchEvent("pointerup", { pointerId: 1, pointerType: "touch", clientX: 80, clientY: 100 })
  await expect(page.getByRole("img", { name: "Gallery model — picture-2.jpg" })).toBeVisible()
})

test("the synthetic click emitted with a swipe does not open the image viewer", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: user }))
  await page.route("**/api/setup/status", route => route.fulfill({ json: { required: false, enabled: false } }))
  await page.route("**/api/tags", route => route.fulfill({ json: [] }))
  await page.route("**/api/favorite-lists/model-memberships**", route => route.fulfill({ json: [] }))
  await page.route("**/api/models/1/navigation", route => route.fulfill({ json: { previous: null, next: null } }))
  await page.route("**/api/models/1", route => route.fulfill({ json: model }))
  await page.goto("/models/1")
  await page.locator(".detail-image-frame").evaluate((frame) => {
    const pointer = (type: string, x: number) => new PointerEvent(type, { bubbles: true, pointerId: 1, pointerType: "touch", clientX: x, clientY: 100 })
    frame.dispatchEvent(pointer("pointerdown", 200))
    frame.dispatchEvent(pointer("pointermove", 80))
    frame.dispatchEvent(pointer("pointerup", 80))
    frame.querySelector<HTMLButtonElement>(".detail-image-button")?.click()
  })
  await expect(page.getByRole("dialog")).toHaveCount(0)
})
