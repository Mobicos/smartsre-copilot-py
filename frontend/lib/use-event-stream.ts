"use client"

import { useCallback, useRef } from "react"
import { parseSSE } from "./sse"

export interface EventStreamHandlers {
  onEvent: (event: string, data: string) => void
  onError?: (err: unknown) => void
  onDone?: () => void
}

/**
 * Browser hook for posting JSON to a SSE endpoint and consuming events.
 * Uses fetch + ReadableStream so we can attach POST bodies (EventSource only supports GET).
 */
export function useEventStream() {
  const controllerRef = useRef<AbortController | null>(null)
  const runningRef = useRef(false)

  const abort = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    runningRef.current = false
  }, [])

  const start = useCallback(async (url: string, body: unknown, handlers: EventStreamHandlers) => {
    abort()
    const ctrl = new AbortController()
    controllerRef.current = ctrl
    runningRef.current = true
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }
      for await (const msg of parseSSE(res.body, ctrl.signal)) {
        if (ctrl.signal.aborted) break
        handlers.onEvent(msg.event, msg.data)
      }
      handlers.onDone?.()
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") return
      handlers.onError?.(err)
    } finally {
      runningRef.current = false
      controllerRef.current = null
    }
  }, [abort])

  const isRunning = () => runningRef.current

  return { start, abort, isRunning }
}
