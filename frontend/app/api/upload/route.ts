import { NextResponse } from "next/server"
import { BACKEND_URL, BACKEND_API_KEY } from "@/lib/backend"
import { normalizeUploadResponse } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function POST(req: Request) {
  try {
    // Forward multipart/form-data as-is to the FastAPI /api/upload endpoint.
    const formData = await req.formData()
    const headers = new Headers()
    if (BACKEND_API_KEY) headers.set("X-API-Key", BACKEND_API_KEY)
    const upstream = await fetch(`${BACKEND_URL}/api/upload`, {
      method: "POST",
      body: formData as unknown as BodyInit,
      headers,
    })
    const text = await upstream.text()
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { raw: text }
    }
    return NextResponse.json(normalizeUploadResponse(payload), { status: upstream.status })
  } catch (err) {
    return NextResponse.json(
      { error: (err as Error).message ?? "backend unreachable" },
      { status: 502 },
    )
  }
}
