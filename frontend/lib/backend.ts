/**
 * Server-side backend configuration for the FastAPI SmartSRE Copilot service.
 * Used only inside Next.js Route Handlers (BFF). The browser never sees the API key.
 */
export const BACKEND_URL = process.env.SMARTSRE_BACKEND_URL || "http://localhost:9900"
export const BACKEND_API_KEY = process.env.SMARTSRE_API_KEY || ""

export function buildHeaders(extra: Record<string, string> = {}): Headers {
  const headers = new Headers(extra)
  if (BACKEND_API_KEY) headers.set("X-API-Key", BACKEND_API_KEY)
  return headers
}

export async function backendFetch(path: string, init: RequestInit = {}) {
  const headers = buildHeaders(
    (init.headers as Record<string, string> | undefined) ?? {},
  )
  if (init.body && !headers.has("content-type") && typeof init.body === "string") {
    headers.set("content-type", "application/json")
  }
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers, cache: "no-store" })
}
