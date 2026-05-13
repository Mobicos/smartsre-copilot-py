"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { CheckCircle2, Loader2, PlayCircle, RefreshCw, XCircle } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import type {
  RegressionEvaluation,
  RegressionScenario,
} from "@/lib/scenario-regression-types"
import { cn } from "@/lib/utils"

export function ScenarioRegressionConsole() {
  const [scenarios, setScenarios] = useState<RegressionScenario[]>([])
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("")
  const [runId, setRunId] = useState("")
  const [evaluation, setEvaluation] = useState<RegressionEvaluation | null>(null)
  const [loading, setLoading] = useState(true)
  const [evaluating, setEvaluating] = useState(false)

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId) ?? null,
    [scenarios, selectedScenarioId],
  )

  const loadScenarios = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/scenario-regression/scenarios", { cache: "no-store" })
      const data = (await res.json()) as RegressionScenario[] | { error?: string }
      if (!res.ok) {
        throw new Error("error" in data && data.error ? data.error : `HTTP ${res.status}`)
      }
      const items = Array.isArray(data) ? data : []
      setScenarios(items)
      setSelectedScenarioId((current) => current || items[0]?.id || "")
    } catch (err) {
      toast.error((err as Error).message || "加载场景失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadScenarios()
  }, [loadScenarios])

  const evaluate = useCallback(async () => {
    if (!selectedScenarioId || !runId.trim()) {
      toast.error("请选择场景并输入运行 ID")
      return
    }
    setEvaluating(true)
    try {
      const res = await fetch("/api/scenario-regression/evaluations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          scenario_id: selectedScenarioId,
          run_id: runId.trim(),
        }),
      })
      const data = (await res.json()) as RegressionEvaluation | { error?: string; detail?: string }
      if (!res.ok) {
        throw new Error(
          ("error" in data && data.error) || ("detail" in data && data.detail) || `HTTP ${res.status}`,
        )
      }
      setEvaluation(data as RegressionEvaluation)
      toast.success(`Scenario ${(data as RegressionEvaluation).status}`)
    } catch (err) {
      toast.error((err as Error).message || "评估失败")
    } finally {
      setEvaluating(false)
    }
  }, [runId, selectedScenarioId])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">场景回归</h1>
          <Button variant="outline" size="sm" onClick={() => void loadScenarios()}>
            <RefreshCw className="size-4" /> 刷新
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-3">
            {scenarios.map((scenario) => {
              const active = scenario.id === selectedScenarioId
              return (
                <button
                  key={scenario.id}
                  type="button"
                  onClick={() => setSelectedScenarioId(scenario.id)}
                  className={cn(
                    "w-full rounded-md border bg-card p-4 text-left transition-colors",
                    active ? "border-primary" : "border-border hover:bg-muted/40",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                          {scenario.priority}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {scenario.id}
                        </span>
                      </div>
                      <h2 className="mt-2 text-base font-semibold">{scenario.title}</h2>
                    </div>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                    {scenario.goal}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {scenario.required_event_types.map((eventType) => (
                      <span
                        key={eventType}
                        className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                      >
                        {eventType}
                      </span>
                    ))}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">评估运行</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="rounded-md bg-muted/50 p-3">
                  <p className="text-sm font-medium">
                    {selectedScenario?.title || "未选择场景"}
                  </p>
                  <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                    {selectedScenario?.goal}
                  </p>
                </div>
                <Input
                  value={runId}
                  onChange={(event) => setRunId(event.target.value)}
                  placeholder="Agent 运行 ID"
                  className="font-mono"
                />
                <Button
                  className="w-full"
                  onClick={() => void evaluate()}
                  disabled={evaluating}
                >
                  {evaluating ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <PlayCircle className="size-4" />
                  )}
                  评估
                </Button>
              </CardContent>
            </Card>

            {evaluation && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between gap-3 text-base">
                    <span>结果</span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        evaluation.status === "passed"
                          ? "bg-success/10 text-success"
                          : "bg-destructive/10 text-destructive",
                      )}
                    >
                      {evaluation.status}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <Metric label="得分" value={`${Math.round(evaluation.score * 100)}%`} />
                    <Metric label="事件" value={evaluation.summary.event_count ?? 0} />
                    <Metric label="失败" value={evaluation.summary.failed_checks ?? 0} />
                  </div>
                  <div className="space-y-2">
                    {evaluation.checks.map((check) => (
                      <div
                        key={check.name}
                        className="flex items-start gap-2 rounded-md border border-border p-2"
                      >
                        {check.passed ? (
                          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
                        ) : (
                          <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                        )}
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs">{check.name}</p>
                          <p className="text-xs text-muted-foreground">{check.message}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-border p-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-sm font-semibold">{value}</p>
    </div>
  )
}
