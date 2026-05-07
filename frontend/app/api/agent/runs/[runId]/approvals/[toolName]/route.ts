import { NextResponse } from "next/server"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"
import { backendErrorStatus, backendFetch } from "@/lib/backend"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(
  req: Request,
  { params }: { params: Promise<{ runId: string; toolName: string }> },
) {
  const { runId, toolName } = await params
  try {
    const res = await backendFetch(
      `/api/agent/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(toolName)}`,
      {
        method: "POST",
        body: await req.text(),
      },
    )
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
