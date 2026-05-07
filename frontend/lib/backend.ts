/**
 * Server-side backend configuration for the FastAPI SmartSRE Copilot service.
 * Used only inside Next.js Route Handlers (BFF). The browser never sees the API key.
 */
export const BACKEND_URL = process.env.SMARTSRE_BACKEND_URL || "http://localhost:9900"
export const BACKEND_API_KEY = process.env.SMARTSRE_API_KEY || ""
export const BACKEND_TIMEOUT_MS = Number(process.env.SMARTSRE_BACKEND_TIMEOUT_MS || "30000")

export class BackendTimeoutError extends Error {
  constructor(path: string) {
    super(`Backend request timed out after ${BACKEND_TIMEOUT_MS}ms: ${path}`)
    this.name = "BackendTimeoutError"
  }
}

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
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS)
  try {
    return await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: controller.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new BackendTimeoutError(path)
    }
    throw err
  } finally {
    clearTimeout(timeout)
  }
}

export function backendErrorStatus(err: unknown): number {
  return err instanceof BackendTimeoutError ? 504 : 502
}
