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
  schema?: Record<string, unknown> | null
  risk_level?: string
  owner?: string
  allowed_scopes?: string[]
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
  goal?: string
  final_report?: string
  error_message?: string | null
  runtime_version?: string | null
  trace_id?: string | null
  approval_state?: string | null
  metrics?: NativeAgentRunMetrics
  created_at?: string
  updated_at?: string
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

export interface NativeAgentRunMetrics {
  runtime_version?: string
  trace_id?: string
  model_name?: string
  steps?: number
  step_count?: number
  tool_calls?: number
  tool_call_count?: number
  latency_ms?: number | null
  error_type?: string | null
  error_count?: number
  approval_state?: string
  retrieval_count?: number
  decision_count?: number
  approval_count?: number
  resume_count?: number
  recovery_count?: number
  handoff_count?: number
  token_usage?: unknown
  cost?: unknown
  cost_estimate?: number | null
  cost_estimate_usd?: number | null
  cost_estimate_source?: string
  runtime_safety?: unknown
  event_counts?: Record<string, number>
}

export interface NativeAgentReplay {
  run?: NativeAgentRun
  summary?: {
    status?: string
    latest_status?: string
    event_count?: number
    tool_call_count?: number
    tool_result_count?: number
    decision_count?: number
    approval_count?: number
    approval_resume_count?: number
    recovery_count?: number
  }
  events?: NativeAgentEvent[]
  tool_calls?: NativeAgentEvent[]
  tool_results?: NativeAgentEvent[]
  tool_trajectory?: Array<{
    tool_name?: string
    call?: NativeAgentEvent | null
    result?: NativeAgentEvent | null
    approval_state?: string | null
    policy?: Record<string, unknown> | null
    execution_status?: string | null
  }>
  decision_events?: NativeAgentEvent[]
  approval_decisions?: NativeAgentEvent[]
  approval_resumes?: NativeAgentEvent[]
  approval_resumed_tool_results?: NativeAgentEvent[]
  recovery_events?: NativeAgentEvent[]
  knowledge_citations?: unknown[]
  final_report?: string | null
  feedback?: unknown[]
  metrics?: NativeAgentRunMetrics
}

export interface NativeAgentApproval {
  run_id: string
  goal?: string
  tool_name: string
  arguments?: Record<string, unknown>
  policy?: Record<string, unknown>
  governance?: Record<string, unknown>
  status: "pending" | "approved" | "rejected" | string
  comment?: string | null
  created_at?: string
  decided_at?: string | null
  resume_status?: string | null
  resume_reason?: string | null
  resume_checkpoint_status?: string | null
  resume_execution_status?: string | null
  resumed_at?: string | null
}

export interface NativeAgentDecisionState {
  run_id: string
  decisions?: NativeAgentEvent[]
  approval_decisions?: NativeAgentEvent[]
  approval_resume?: NativeAgentEvent[]
  recovery_events?: NativeAgentEvent[]
  latest_status?: string
}
