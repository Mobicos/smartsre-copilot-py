export interface RegressionScenario {
  id: string
  title: string
  priority: string
  goal: string
  expected_signals: string[]
  required_event_types: string[]
  blocked_terms: string[]
  min_tool_calls: number
}

export interface RegressionCheck {
  name: string
  passed: boolean
  message: string
}

export interface RegressionEvaluation {
  scenario: RegressionScenario
  run_id: string
  status: "passed" | "failed" | string
  score: number
  checks: RegressionCheck[]
  summary: {
    run_status?: string
    event_count?: number
    tool_call_count?: number
    failed_checks?: number
  }
}
