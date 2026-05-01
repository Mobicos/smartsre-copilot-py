import { NextResponse } from "next/server"
import { backendFetch } from "@/lib/backend"
import { unwrapBackendEnvelope } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  return proxyJson("/api/workspaces", { method: "GET" })
}

export async function POST(req: Request) {
  return proxyJson("/api/workspaces", {
    method: "POST",
    body: await req.text(),
  })
}

async function proxyJson(path: string, init: RequestInit) {
  try {
    const res = await backendFetch(path, init)
    const payload = await readPayload(res)
    return NextResponse.json(unwrapBackendEnvelope(payload), { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: 502 },
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
