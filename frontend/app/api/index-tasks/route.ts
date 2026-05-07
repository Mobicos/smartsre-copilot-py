import { NextResponse } from "next/server"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"
import { backendErrorStatus, backendFetch } from "@/lib/backend"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET(req: Request) {
  try {
    const url = new URL(req.url)
    const params = url.searchParams.toString()
    const path = params ? `/api/index_tasks?${params}` : "/api/index_tasks"
    const res = await backendFetch(path, { method: "GET" })
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
