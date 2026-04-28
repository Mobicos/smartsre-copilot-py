"use client"

import { useEffect, useState } from "react"
import type { HealthPayload } from "./types"

export function useHealth(intervalMs = 15000) {
  const [data, setData] = useState<HealthPayload | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    async function tick() {
      try {
        const res = await fetch("/api/health", { cache: "no-store" })
        const json = (await res.json()) as HealthPayload
        if (!cancelled) {
          setData(json)
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setData({ ok: false, status: 0, error: (err as Error).message })
          setLoading(false)
        }
      }
    }

    tick()
    timer = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      if (timer) clearInterval(timer)
    }
  }, [intervalMs])

  return { data, loading }
}
