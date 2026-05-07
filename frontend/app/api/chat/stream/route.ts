import { backendErrorStatus, backendFetch } from "@/lib/backend"
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
    // Transform the upstream SSE stream to ensure proper formatting
    // Backend uses \r\n\r\n as SSE block separator (sse-starlette default)
    const encoder = new TextEncoder()
    const decoder = new TextDecoder()
    const transformed = new ReadableStream({
      async start(controller) {
        const reader = upstream.body!.getReader()
        let buffer = ""
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            // Process complete SSE blocks (handle both \r\n\r\n and \n\n separators)
            const blocks = buffer.split(/\r\n\r\n|\n\n/)
            buffer = blocks.pop() || ""
            for (const block of blocks) {
              if (block.trim()) {
                controller.enqueue(encoder.encode(block + "\n\n"))
              }
            }
          }
          // Flush remaining
          if (buffer.trim()) {
            controller.enqueue(encoder.encode(buffer + "\n\n"))
          }
        } finally {
          controller.close()
        }
      },
    })
    return new Response(transformed, {
      status: upstream.status,
      headers: sseHeaders(),
    })
  } catch (err) {
    const msg = (err as Error).message ?? "backend unreachable"
    const body = `event: error\ndata: ${JSON.stringify({ error: msg })}\n\n`
    return new Response(body, { status: backendErrorStatus(err), headers: sseHeaders() })
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
