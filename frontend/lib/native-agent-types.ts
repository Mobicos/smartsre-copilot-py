export interface NativeWorkspace {
  id: string
  name: string
  description?: string | null
  created_at?: string
  updated_at?: string
}

export interface NativeScene {
  id: string
  workspace_id: string
  name: string
  description?: string | null
  knowledge_base_ids?: string[]
  tool_names?: string[]
  agent_config?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

export interface NativeTool {
  name: string
  description?: string
  policy?: {
    enabled?: boolean
    risk_level?: string
    approval_required?: boolean
    [key: string]: unknown
  } | null
}

export interface NativeAgentRun {
  run_id: string
  status?: string
  final_report?: string
}

export interface NativeAgentEvent {
  id?: number
  run_id?: string
  type?: string
  message?: string
  payload?: unknown
  created_at?: string
  [key: string]: unknown
}
