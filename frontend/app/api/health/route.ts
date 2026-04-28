import { NextResponse } from "next/server"
import { backendFetch } from "@/lib/backend"
import { normalizeHealthPayload } from "@/lib/api-contracts"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  try {
    const res = await backendFetch("/health", { method: "GET" })
    const text = await res.text()
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { raw: text }
    }
    return NextResponse.json(
      { ok: res.ok, status: res.status, payload: normalizeHealthPayload(payload) },
      { status: 200 },
    )
  } catch (err) {
    return NextResponse.json(
      { ok: false, status: 0, error: (err as Error).message ?? "unreachable" },
      { status: 200 },
    )
  }
}
