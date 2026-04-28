import { NextResponse } from "next/server"
import { backendFetch } from "@/lib/backend"
import {
  normalizeChatResponse,
  toBackendChatRequest,
  type ChatRequestPayload,
} from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(req: Request) {
  try {
    const payload = (await req.json()) as ChatRequestPayload
    const body = JSON.stringify(toBackendChatRequest(payload))
    const res = await backendFetch("/api/chat", { method: "POST", body })
    const text = await res.text()
    let backendPayload: unknown
    try {
      backendPayload = JSON.parse(text)
    } catch {
      backendPayload = { raw: text }
    }
    return NextResponse.json(normalizeChatResponse(backendPayload), { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: 502 },
    )
  }
}
