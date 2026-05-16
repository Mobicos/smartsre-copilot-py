# AgentOps Metrics & Release Gate

## Problem Statement

The AI Native Agent Runtime (Phases 6–10) is feature-complete. A Release Gate audit found 4 gaps in the metrics and observability layer. The runtime *behaves* correctly but cannot *prove* it meets release criteria because the measurement infrastructure is missing.

| Criterion | Target | Current Status |
|-----------|--------|----------------|
| goal_completion_rate | > 80% | Per-run scoring exists; no aggregate metric |
| unnecessary_tool_call_ratio | < 10% | No metric for duplicate/empty-result calls |
| approval_override_rate | < 5% | Enforcement solid; no bypass counter |
| P95 latency | < 60s | Only avg/max; no percentile |

## Proposed Metrics

### Per-Run Metrics (added to MetricsCollector)

**recovery_count** (int)
Count of recovery events in a run. Signals how often the agent had to self-correct.
```
recovery_count = count(events where type == "recovery")
```

**empty_result_count** (int)
Count of tool calls that returned non-success status or empty output. These are tool calls that consumed budget without producing useful evidence.
```
empty_result_count = count(tool_result events where status != "success" or output is empty)
```

**duplicate_tool_call_count** (int)
Count of tool calls where the same (tool_name, arguments) signature appeared more than once. Duplicate calls waste budget and indicate planning failures.
```
signatures = [(tool_name, json(args)) for each tool_call event]
duplicate_tool_call_count = count(signature appears > 1 time) - count(unique signatures that appear > 1)
```

**step_latencies** (JSON)
Per-step wall-clock timing derived from event `step_index` + `created_at`.
```json
{
  "count": 5,
  "avg_ms": 12000,
  "max_ms": 25000,
  "p95_ms": 23000,
  "steps": [
    {"step_index": 0, "duration_ms": 8000},
    {"step_index": 1, "duration_ms": 12000}
  ]
}
```

**regression_score** (float | null)
Per-run regression evaluation score, populated by the aggregate service.

### Aggregate Release Gate Metrics (computed by AgentMetricsService)

**goal_completion_rate**
For each completed run, evaluate against the best-matching golden scenario using `ScenarioRegressionService.evaluate_run()`. Return the average score across all evaluated runs.
```
goal_completion_rate = mean(max_score_per_run for each run)
```

**unnecessary_tool_call_ratio**
Total (duplicate + empty) tool calls divided by total tool calls across the window.
```
unnecessary_tool_call_ratio = sum(duplicate + empty) / sum(tool_call_count)
```

**approval_override_rate**
Count of runs where `approval_state == "required"` but no `approval_decision` event exists and the run completed successfully (bypassed approval).
```
approval_override_rate = override_count / approval_required_count
```

**p95_latency_ms**
95th percentile of `latency_ms` values across completed runs in the window.

## Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| goal_completion_rate | >= 0.80 | 80% of runs should pass their best-matching scenario |
| unnecessary_tool_call_ratio | <= 0.10 | At most 10% of tool calls should be wasted |
| approval_override_rate | <= 0.05 | High-risk tools must not execute without approval |
| p95_latency_ms | <= 60000 | 95% of runs must complete within 60 seconds |

## Data Flow

```text
BoundedReActLoop
  -> per-step events (tool_call, tool_result, recovery) persisted to agent_events
  -> MetricsCollector.persist(run_id)
      -> collect_run_metrics(run_id) derives all per-run metrics
      -> update_run_metrics(run_id, **metrics) persists to agent_runs
      -> observe_agent_run() records Prometheus histograms

AgentMetricsService.compute_release_gate()
  -> list_runs(limit=N) fetches recent runs
  -> for each run: evaluate against scenarios (goal_completion)
  -> aggregate: unnecessary ratio, approval override, P95 latency
  -> returns gate_pass boolean + all metrics + thresholds

GET /agent/metrics/release-gate
  -> AgentMetricsService.compute_release_gate()
  -> JSON response with all gate metrics
```

## API Contract

### GET /api/v1/agent/metrics/release-gate

**Query Parameters:**
- `limit` (int, default 100) — number of recent runs to evaluate

**Response:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "window_size": 100,
    "completed_runs": 85,
    "goal_completion_rate": 0.87,
    "unnecessary_tool_call_ratio": 0.06,
    "approval_override_rate": 0.0,
    "p95_latency_ms": 42000,
    "gate_thresholds": {
      "goal_completion_rate_min": 0.80,
      "unnecessary_tool_call_ratio_max": 0.10,
      "approval_override_rate_max": 0.05,
      "p95_latency_ms_max": 60000
    },
    "gate_pass": true
  }
}
```

### GET /api/v1/agent/metrics/summary

**Query Parameters:**
- `limit` (int, default 50) — number of recent runs

**Response:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total_runs": 50,
    "completed": 42,
    "failed": 5,
    "running": 3,
    "avg_latency_ms": 28000,
    "avg_step_count": 4,
    "total_tool_calls": 180,
    "total_tokens": 125000,
    "total_cost_usd": 0.42,
    "avg_recovery_count": 0.3
  }
}
```

## Prometheus Metrics

| Metric Name | Type | Buckets/Labels |
|-------------|------|----------------|
| smartsre_agent_run_latency_seconds | Histogram | (1, 5, 10, 15, 30, 45, 60, 90, 120, 300) |
| smartsre_agent_token_usage_total | Histogram | (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000) |
| smartsre_agent_cost_estimate_usd | Histogram | (0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0) |
| smartsre_agent_step_count | Histogram | (1, 2, 3, 4, 5, 6, 7, 8, 10) |
| smartsre_agent_release_gate | Gauge | label: metric_name |

## DB Schema Changes

New columns on `agent_runs`:

| Column | Type | Default |
|--------|------|---------|
| recovery_count | INTEGER | 0 |
| empty_result_count | INTEGER | 0 |
| duplicate_tool_call_count | INTEGER | 0 |
| step_latencies | JSONB | NULL |
| regression_score | DOUBLE PRECISION | NULL |

Index: `idx_agent_runs_latency_ms ON agent_runs(latency_ms)`

## Testing Strategy

- Unit tests for all new MetricsCollector functions (recovery, empty, duplicate, step_latencies)
- Unit tests for AgentMetricsService aggregate calculations with mock repositories
- Unit tests verifying gate_pass logic (all pass vs any fail)
- Existing golden scenario tests validate the regression scoring backbone
- Frontend lint + typecheck for new panel component
