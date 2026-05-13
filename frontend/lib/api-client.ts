"use client"

export interface ApiClientOptions extends RequestInit {
  retries?: number
}

export async function apiClient<T>(url: string, options: ApiClientOptions = {}): Promise<T> {
  const { retries = 0, ...init } = options
  const headers = new Headers(init.headers)
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json")
  }

  let lastError: unknown
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(url, {
        ...init,
        headers,
        cache: init.cache ?? "no-store",
      })
      const payload = (await response.json().catch(() => undefined)) as
        | T
        | { error?: string; detail?: string; message?: string; data?: T }
        | undefined
      if (!response.ok) {
        throw new Error(apiErrorMessage(payload, response.status))
      }
      return unwrapPayload<T>(payload)
    } catch (error) {
      if (isAbortError(error) || attempt >= retries) {
        throw error
      }
      lastError = error
    }
  }
  throw lastError instanceof Error ? lastError : new Error("请求失败")
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError"
}

function unwrapPayload<T>(payload: unknown): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as { data: T }).data
  }
  return payload as T
}

function apiErrorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === "object") {
    const data = payload as { error?: string; detail?: string; message?: string }
    return data.error || data.detail || data.message || `HTTP ${status}`
  }
  return `HTTP ${status}`
}
