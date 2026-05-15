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
    await expect(page.getByRole("main")).toBeVisible()
    await expect(page.getByRole("button", { name: /运行/ })).toBeVisible()
  })

  test("agent history page loads", async ({ page }) => {
    await page.goto("/agent/history")
    await expect(page.getByRole("heading", { name: "历史记录" }).first()).toBeVisible()
  })

  test("agent tools page loads", async ({ page }) => {
    await page.goto("/agent/tools")
    await expect(page.getByText("get_current_time").first()).toBeVisible({
      timeout: 15_000,
    })
  })

  test("agent approvals page loads", async ({ page }) => {
    await page.goto("/agent/approvals")
    await expect(page.getByRole("heading", { name: "审批" }).first()).toBeVisible()
  })

  test("404 page renders for unknown routes", async ({ page }) => {
    const response = await page.goto("/this-does-not-exist")
    expect(response?.status()).toBe(404)
    await expect(page.getByText("页面未找到")).toBeVisible()
  })

  test("health API returns 200", async ({ request }) => {
    const response = await request.get("/api/health")
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data).toHaveProperty("status")
  })

  test("contracts API returns current OpenAPI summary", async ({ request }) => {
    const response = await request.get("/api/contracts/openapi")
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data).toHaveProperty("current")
    expect(data.current.operation_count).toBeGreaterThan(0)
  })
})
