import { backendFetch } from "@/lib/backend"
import { toBackendChatRequest, type ChatRequestPayload } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(req: Request) {
  try {
    const payload = (await req.json()) as ChatRequestPayload
    const body = JSON.stringify(toBackendChatRequest(payload))
    const upstream = await backendFetch("/api/chat_stream", {
      method: "POST",
      body,
      headers: { "content-type": "application/json", accept: "text/event-stream" },
    })
    if (!upstream.body) {
      return new Response("event: error\ndata: empty upstream\n\n", {
        status: 502,
        headers: sseHeaders(),
      })
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: sseHeaders(),
    })
  } catch (err) {
    const msg = (err as Error).message ?? "backend unreachable"
    const body = `event: error\ndata: ${JSON.stringify({ error: msg })}\n\n`
    return new Response(body, { status: 502, headers: sseHeaders() })
  }
}

function sseHeaders() {
  return {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    connection: "keep-alive",
    "x-accel-buffering": "no",
  }
}
