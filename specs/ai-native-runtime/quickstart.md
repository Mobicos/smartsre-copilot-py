# Quickstart: AI Native Agent Runtime

**Date**: 2026-05-13
**Spec**: [spec.md](./spec.md)

## Prerequisites

- Docker Compose running (postgres, redis, minio)
- Database migrated: `make db-upgrade`
- MCP tools running: `make start-cls && make start-monitor`

## Validation Scenarios

### Scenario 1: Bounded ReAct Loop (US1)

```bash
# Start dev server
make dev

# In another terminal, initiate diagnosis
curl -s -X POST http://localhost:9900/api/v1/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"scene_id": 1, "goal": "diagnose why API response time is slow"}' \
  | python3 -m json.tool

# Check run status (poll until completed)
curl -s http://localhost:9900/api/v1/agent/runs/{run_id} | python3 -m json.tool

# Verify:
# - status = "completed"
# - step_count >= 2
# - token_usage is non-empty JSON
# - cost_estimate is non-empty JSON
# - final_report contains evidence + recommendations
```

### Scenario 2: Step Budget Enforcement (US1)

```bash
# Set low step budget for testing
# In .env: AGENT_MAX_STEPS=3

# Initiate complex diagnosis
curl -s -X POST http://localhost:9900/api/v1/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"scene_id": 1, "goal": "full infrastructure audit"}'

# Verify:
# - step_count = 3 (budget enforced)
# - status = "completed" (bounded_report, not crashed)
# - report contains "budget_exceeded" in termination_reason
```

### Scenario 3: Dual Provider Switch (US2)

```bash
# With Deterministic provider (default)
# .env: AGENT_DECISION_PROVIDER=deterministic
make dev
curl -s -X POST http://localhost:9900/api/v1/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"scene_id": 1, "goal": "check CPU usage"}'
# Verify: decision_provider = "deterministic" in run result

# Switch to Qwen provider
# .env: AGENT_DECISION_PROVIDER=qwen
# Restart dev server
curl -s -X POST http://localhost:9900/api/v1/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"scene_id": 1, "goal": "check CPU usage"}'
# Verify: decision_provider = "qwen" in run result
# Verify: reasoning_summary is non-empty
```

### Scenario 4: Recovery on Tool Failure (US4)

```bash
# Run the recovery integration test
uv run pytest tests/integration/test_recovery.py -v

# Verify:
# - Agent entered recovery after tool failure
# - recovery event recorded with strategy
# - Final report indicates partial findings (not forged conclusions)
```

### Scenario 5: Metrics Collection (US3)

```bash
# Execute a run
curl -s -X POST http://localhost:9900/api/v1/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"scene_id": 1, "goal": "diagnose disk usage"}'

# Query database
uv run python -c "
import asyncio
from app.platform.persistence.database import get_engine
from sqlalchemy import text

async def check():
    async with get_engine().connect() as conn:
        result = await conn.execute(
            text('SELECT token_usage, cost_estimate, step_count, decision_provider '
                 'FROM agent_runs ORDER BY created_at DESC LIMIT 1')
        )
        row = result.fetchone()
        print(f'token_usage: {row[0]}')
        print(f'cost_estimate: {row[1]}')
        print(f'step_count: {row[2]}')
        print(f'decision_provider: {row[3]}')
        assert row[0] is not None, 'token_usage is None!'
        assert row[1] is not None, 'cost_estimate is None!'
        print('All metrics non-None - PASS')

asyncio.run(check())
"
```

### Scenario 6: Golden Scenario Eval (Full Regression)

```bash
# Run all golden scenarios
uv run pytest tests/agent_scenarios/ -v

# Expected: 6 scenarios pass
# 1. CPU high diagnosis
# 2. 5xx spike diagnosis
# 3. Slow response diagnosis
# 4. Disk full diagnosis
# 5. Deploy regression diagnosis
# 6. Dependency failure diagnosis
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Agent hangs | Check step_budget in config, verify loop termination |
| token_usage still None | Verify MetricsCollector integration in loop.py |
| Provider fallback not working | Check Qwen API key in .env, check provider_fallback event |
| Recovery not triggered | Verify EvidenceAssessment returns INSUFFICIENT |
| Tests fail | Run `make verify` to check full quality gate |
