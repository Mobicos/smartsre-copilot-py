import { NextResponse } from "next/server"
import { backendErrorStatus, backendFetch } from "@/lib/backend"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await params
  try {
    const res = await backendFetch(`/api/index_tasks/${encodeURIComponent(taskId)}`, {
      method: "GET",
    })
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
