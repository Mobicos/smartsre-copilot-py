export interface BackendEnvelope<T> {
  code?: number
  message?: string
  data?: T
}

export interface ChatRequestPayload {
  id?: string
  Id?: string
  session_id?: string
  sessionId?: string
  question?: string
  Question?: string
  query?: string
}

export interface BackendChatRequest {
  Id: string
  Question: string
}

export interface BackendChatData {
  answer?: string
  toolEvents?: unknown[]
  exchangeId?: string
}

export interface ChatResponsePayload {
  answer: string
  toolEvents: unknown[]
  exchangeId?: string
  raw?: unknown
}

export interface BackendIndexingData {
  filename?: string
  file_path?: string
  size?: number
  indexing?: {
    taskId?: string
    status?: string
  }
}

export function unwrapBackendEnvelope<T>(payload: unknown): T | undefined {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as BackendEnvelope<T>).data
  }
  return payload as T
}

export function toBackendChatRequest(payload: ChatRequestPayload): BackendChatRequest {
  const id = payload.Id ?? payload.id ?? payload.session_id ?? payload.sessionId
  const question = payload.Question ?? payload.question ?? payload.query

  if (!id || !question) {
    throw new Error("Chat requests require both session id and question")
  }

  return { Id: id, Question: question }
}

export function normalizeChatResponse(payload: unknown): ChatResponsePayload {
  const data = unwrapBackendEnvelope<BackendChatData>(payload)
  if (data && typeof data === "object") {
    return {
      answer: typeof data.answer === "string" ? data.answer : "",
      toolEvents: Array.isArray(data.toolEvents) ? data.toolEvents : [],
      exchangeId: typeof data.exchangeId === "string" ? data.exchangeId : undefined,
      raw: payload,
    }
  }

  return { answer: "", toolEvents: [], raw: payload }
}

export function normalizeHealthPayload(payload: unknown): unknown {
  return unwrapBackendEnvelope(payload)
}

export function normalizeUploadResponse(payload: unknown) {
  const data = unwrapBackendEnvelope<BackendIndexingData>(payload)
  if (data && typeof data === "object") {
    return {
      filename: data.filename,
      filePath: data.file_path,
      size: data.size,
      taskId: data.indexing?.taskId,
      status: data.indexing?.status,
      raw: payload,
    }
  }

  return { raw: payload }
}
