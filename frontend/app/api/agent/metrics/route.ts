import { NextResponse } from "next/server"
import { backendErrorStatus, backendFetch } from "@/lib/backend"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET(req: Request) {
  try {
    const url = new URL(req.url)
    const limit = url.searchParams.get("limit")
    const endpoint = url.searchParams.get("endpoint") ?? "release-gate"

    const backendPath =
      endpoint === "summary"
        ? `/api/agent/metrics/summary`
        : `/api/agent/metrics/release-gate`

    const path = limit ? `${backendPath}?limit=${encodeURIComponent(limit)}` : backendPath

    const res = await backendFetch(path)
    const text = await res.text()
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { raw: text }
    }
    return NextResponse.json(unwrapBackendEnvelope(payload), { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: backendErrorStatus(err) },
    )
  }
}
