/**
 * Minimal Server-Sent Events parser. Works on both edge and node runtimes.
 * Yields { event, data } objects parsed from a ReadableStream<Uint8Array>.
 */
export type SSEMessage = { event: string; data: string; id?: string }

export async function* parseSSE(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEMessage> {
  const reader = stream.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""

  try {
    while (true) {
      if (signal?.aborted) return
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let sepIdx: number
      // Process complete event blocks (separated by blank line)
      while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sepIdx)
        buffer = buffer.slice(sepIdx + 2)
        const msg = parseBlock(block)
        if (msg) yield msg
      }
    }
    // Flush remaining
    if (buffer.trim()) {
      const msg = parseBlock(buffer)
      if (msg) yield msg
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {}
  }
}

function parseBlock(block: string): SSEMessage | null {
  const lines = block.split(/\r?\n/)
  let event = "message"
  const dataLines: string[] = []
  let id: string | undefined

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "")
    if (field === "event") event = value
    else if (field === "data") dataLines.push(value)
    else if (field === "id") id = value
  }
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join("\n"), id }
}

export function tryParseJSON<T = unknown>(s: string): T | string {
  try {
    return JSON.parse(s) as T
  } catch {
    return s
  }
}
