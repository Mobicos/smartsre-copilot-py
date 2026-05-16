"use client"

import { useEffect, useCallback, useState } from "react"
import { Activity, AlertTriangle, CheckCircle2, Clock, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface ReleaseGateMetrics {
  goal_completion_rate: number
  unnecessary_tool_call_ratio: number
  approval_override_rate: number
  p95_latency_ms: number | null
  gate_pass: boolean
  gate_thresholds: Record<string, number>
  total_runs_evaluated: number
}

interface MetricCard {
  key: string
  label: string
  value: string
  passed: boolean
  threshold: string
  icon: typeof Activity
}

const REFRESH_INTERVAL_MS = 30_000

export default function AgentMetricsPanel() {
  const [metrics, setMetrics] = useState<ReleaseGateMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchMetrics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch("/api/agent/metrics?endpoint=release-gate&limit=200")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json()
      setMetrics(body as ReleaseGateMetrics)
      setLastRefresh(new Date())
    } catch (err) {
      setError((err as Error).message ?? "Failed to load metrics")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMetrics()
    const timer = setInterval(fetchMetrics, REFRESH_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [fetchMetrics])

  const cards = buildMetricCards(metrics)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">AgentOps Release Gate</CardTitle>
          {metrics && (
            <Badge variant={metrics.gate_pass ? "default" : "destructive"}>
              {metrics.gate_pass ? "PASS" : "FAIL"}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-muted-foreground text-xs">
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={fetchMetrics}
            disabled={loading}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="text-destructive flex items-center gap-2 py-4 text-sm">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}
        {!error && metrics && (
          <div className="grid grid-cols-2 gap-3">
            {cards.map((card) => (
              <MetricCardItem key={card.key} card={card} />
            ))}
          </div>
        )}
        {!error && loading && !metrics && (
          <div className="text-muted-foreground py-4 text-center text-sm">加载中...</div>
        )}
        {metrics && (
          <div className="text-muted-foreground mt-3 text-xs">
            已评估 {metrics.total_runs_evaluated} 次运行
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function MetricCardItem({ card }: { card: MetricCard }) {
  const Icon = card.icon
  return (
    <div
      className={cn(
        "rounded-lg border p-3 transition-colors",
        card.passed
          ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
          : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs font-medium">{card.label}</span>
        {card.passed ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
        ) : (
          <AlertTriangle className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
        )}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-lg font-semibold">{card.value}</span>
        <span className="text-muted-foreground text-xs">/ {card.threshold}</span>
      </div>
    </div>
  )
}

function buildMetricCards(m: ReleaseGateMetrics | null): MetricCard[] {
  if (!m) return []

  return [
    {
      key: "goal_completion_rate",
      label: "目标完成率",
      value: formatPercent(m.goal_completion_rate),
      passed: m.goal_completion_rate >= (m.gate_thresholds.goal_completion_rate_min ?? 0.8),
      threshold: `≥${formatPercent(m.gate_thresholds.goal_completion_rate_min ?? 0.8)}`,
      icon: Activity,
    },
    {
      key: "unnecessary_tool_call_ratio",
      label: "冗余工具调用比",
      value: formatPercent(m.unnecessary_tool_call_ratio),
      passed:
        m.unnecessary_tool_call_ratio <= (m.gate_thresholds.unnecessary_tool_call_ratio_max ?? 0.1),
      threshold: `≤${formatPercent(m.gate_thresholds.unnecessary_tool_call_ratio_max ?? 0.1)}`,
      icon: AlertTriangle,
    },
    {
      key: "approval_override_rate",
      label: "审批绕过率",
      value: formatPercent(m.approval_override_rate),
      passed:
        m.approval_override_rate <= (m.gate_thresholds.approval_override_rate_max ?? 0.05),
      threshold: `≤${formatPercent(m.gate_thresholds.approval_override_rate_max ?? 0.05)}`,
      icon: Clock,
    },
    {
      key: "p95_latency_ms",
      label: "P95 延迟",
      value: m.p95_latency_ms !== null ? `${(m.p95_latency_ms / 1000).toFixed(1)}s` : "N/A",
      passed:
        m.p95_latency_ms !== null &&
        m.p95_latency_ms <= (m.gate_thresholds.p95_latency_ms_max ?? 60000),
      threshold: `≤${((m.gate_thresholds.p95_latency_ms_max ?? 60000) / 1000).toFixed(0)}s`,
      icon: Clock,
    },
  ]
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}
