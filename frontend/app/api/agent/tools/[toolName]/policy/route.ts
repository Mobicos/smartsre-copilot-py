import { NextResponse } from "next/server"
import { backendErrorStatus, backendFetch } from "@/lib/backend"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

interface Props {
  params: Promise<{ toolName: string }>
}

export async function PATCH(req: Request, { params }: Props) {
  try {
    const { toolName } = await params
    const res = await backendFetch(`/api/tools/${encodeURIComponent(toolName)}/policy`, {
      method: "PATCH",
      body: await req.text(),
    })
    const payload = await readPayload(res)
    return NextResponse.json(unwrapBackendEnvelope(payload), { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: backendErrorStatus(err) },
    )
  }
}

async function readPayload(res: Response): Promise<unknown> {
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return { raw: text }
  }
}
