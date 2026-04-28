export type Role = "user" | "assistant" | "system"

export interface ChatSource {
  title?: string
  source?: string
  score?: number
  snippet?: string
}

export interface ChatMessage {
  id: string
  role: Role
  content: string
  createdAt: number
  streaming?: boolean
  sources?: ChatSource[]
  error?: string
}

export interface ChatSession {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: ChatMessage[]
}

export type AiopsPhase = "idle" | "planning" | "executing" | "replanning" | "reporting" | "done" | "error"

export interface AiopsStep {
  id: string
  index: number
  title: string
  description?: string
  status: "pending" | "running" | "succeeded" | "failed" | "skipped"
  toolCalls: AiopsToolCall[]
  output?: string
  startedAt?: number
  finishedAt?: number
}

export interface AiopsToolCall {
  id: string
  name: string
  args?: unknown
  result?: unknown
  status: "running" | "succeeded" | "failed"
}

export interface AiopsRun {
  id: string
  query: string
  phase: AiopsPhase
  steps: AiopsStep[]
  report?: string
  createdAt: number
  finishedAt?: number
  error?: string
}

export interface IndexingTask {
  id: string
  filename: string
  size: number
  status: "queued" | "processing" | "completed" | "failed_permanently" | "running" | "succeeded" | "failed"
  chunks?: number
  message?: string
  startedAt: number
  finishedAt?: number
}

export interface HealthPayload {
  ok: boolean
  status: number
  payload?: {
    status?: string
    milvus?: string | { status?: string; collection?: string }
    redis?: string
    mcp?: Record<string, string>
    [k: string]: unknown
  }
  error?: string
}
