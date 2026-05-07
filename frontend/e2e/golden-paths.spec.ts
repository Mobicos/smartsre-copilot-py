import { test, expect } from "@playwright/test"

test.describe("Golden paths", () => {
  test("home page loads and redirects to chat", async ({ page }) => {
    await page.goto("/")
    await expect(page).toHaveURL(/\/(chat)?$/)
  })

  test("chat page has input and sidebar", async ({ page }) => {
    await page.goto("/chat")
    await expect(page.locator("nav")).toBeVisible()
  })

  test("agent page loads", async ({ page }) => {
    await page.goto("/agent")
    await expect(page.locator("text=Agent").first()).toBeVisible()
  })

  test("agent history page loads", async ({ page }) => {
    await page.goto("/agent/history")
    await expect(page.locator("text=History").first()).toBeVisible()
  })

  test("agent tools page loads", async ({ page }) => {
    await page.goto("/agent/tools")
    await expect(page.locator("text=Tools").first()).toBeVisible()
  })

  test("agent approvals page loads", async ({ page }) => {
    await page.goto("/agent/approvals")
    await expect(page.locator("text=Approvals").first()).toBeVisible()
  })

  test("404 page renders for unknown routes", async ({ page }) => {
    const response = await page.goto("/this-does-not-exist")
    expect(response?.status()).toBe(404)
    await expect(page.locator("text=not found").first()).toBeVisible()
  })

  test("health API returns 200", async ({ request }) => {
    const response = await request.get("/api/health")
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data).toHaveProperty("status")
  })
})
