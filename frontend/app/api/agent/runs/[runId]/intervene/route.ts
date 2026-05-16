import { NextResponse } from "next/server"
import { backendErrorStatus, backendFetch } from "@/lib/backend"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(
  req: Request,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params
  try {
    const body = (await req.json()) as {
      intervention_type: string
      payload?: Record<string, unknown>
    }
    const res = await backendFetch(`/api/agent/runs/${encodeURIComponent(runId)}/intervene`, {
      method: "POST",
      body: JSON.stringify({
        intervention_type: body.intervention_type,
        payload: body.payload ?? {},
      }),
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
