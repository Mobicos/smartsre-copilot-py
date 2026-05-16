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
  payload?: NativeAgentEventPayload
  created_at?: string
  [key: string]: unknown
}

export interface NativeEvidenceAssessment {
  quality?: "strong" | "partial" | "weak" | "empty" | "conflicting" | "error" | string
  summary?: string
  citations?: Array<Record<string, unknown>>
  confidence?: number
}

export interface NativeDecisionPayload {
  action_type?: string
  reasoning_summary?: string
  selected_tool?: string | null
  selected_action?: string | null
  tool_arguments?: Record<string, unknown>
  expected_evidence?: string[]
  evidence?: NativeEvidenceAssessment
  actual_evidence?: NativeEvidenceAssessment
  confidence?: number
  decision_status?: string
  handoff_reason?: string | null
}

export interface NativeAgentEventPayload {
  goal?: string
  trace_id?: string | null
  memories?: NativeAgentMemory[]
  decision?: NativeDecisionPayload
  hypotheses?: Array<Record<string, unknown>>
  quality?: string
  summary?: string
  confidence?: number
  handoff_reason?: string | null
  verified_facts?: string[]
  inferences?: string[]
  recommendations?: string[]
  [key: string]: unknown
}

export interface NativeAgentMemory {
  memory_id?: string
  run_id?: string | null
  conclusion_text?: string
  conclusion_type?: string
  confidence?: number
  similarity?: number
  metadata?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export interface NativeAgentBadcase {
  feedback_id: string
  run_id: string
  rating: string
  comment?: string | null
  correction?: string | null
  badcase_flag?: boolean
  original_report?: string | null
  review_status?: "pending" | "confirmed" | "rejected" | string
  review_note?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  knowledge_status?: "not_promoted" | "queued" | "processing" | "completed" | string
  knowledge_task_id?: string | null
  knowledge_filename?: string | null
  promoted_at?: string | null
  created_at?: string
  run?: NativeAgentRun
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

export interface NativeToolTrajectory {
  tool_name?: string
  call?: NativeAgentEvent | null
  result?: NativeAgentEvent | null
  approval_state?: string | null
  policy?: Record<string, unknown> | null
  execution_status?: string | null
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
  tool_trajectory?: NativeToolTrajectory[]
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

export interface NativeAgentInterventionRequest {
  intervention_type: "inject_evidence" | "replace_tool_call" | "modify_goal"
  payload: Record<string, unknown>
}

export interface NativeAgentInterventionResponse {
  intervention_id: string
  intervention_type: string
}

export interface NativeAgentDecisionState {
  run_id: string
  goal?: {
    goal?: string
    success_criteria?: string[]
    stop_condition?: Record<string, unknown>
    priority?: string
    scene_id?: string | null
    workspace_id?: string | null
    runtime_safety?: Record<string, unknown> | null
  }
  observations?: Array<Record<string, unknown>>
  hypotheses?: Array<Record<string, unknown>>
  decisions?: NativeDecisionPayload[]
  evidence_assessments?: NativeEvidenceAssessment[]
  tool_trajectory?: NativeToolTrajectory[]
  approval_decisions?: NativeAgentEvent[]
  approval_resume?: NativeAgentEvent[]
  recovery_events?: NativeAgentEvent[]
  handoff?: {
    required?: boolean
    reason?: string | null
    event?: NativeAgentEvent | null
  }
  latest_status?: string
  summary?: {
    decision_count?: number
    observation_count?: number
    evidence_assessment_count?: number
    recovery_count?: number
    tool_call_count?: number
    handoff_required?: boolean
  }
}
