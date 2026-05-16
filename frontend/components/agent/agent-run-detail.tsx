"use client"

import type { ElementType } from "react"
import { useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowLeft,
  Brain,
  CheckCircle2,
  Loader2,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Markdown } from "@/components/markdown"
import { AgentEventTimeline } from "./agent-event-timeline"
import { AgentInterventionPanel } from "./agent-intervention-panel"
import { cn } from "@/lib/utils"
import type {
  NativeAgentDecisionState,
  NativeAgentEvent,
  NativeAgentMemory,
  NativeAgentReplay,
} from "@/lib/native-agent-types"

interface AgentRun {
  run_id: string
  status: string
  goal: string
  final_report?: string | null
  error_message?: string | null
  created_at?: string
  updated_at?: string
}

interface AgentRunDetailProps {
  runId: string
}

export function AgentRunDetail({ runId }: AgentRunDetailProps) {
  const [run, setRun] = useState<AgentRun | null>(null)
  const [events, setEvents] = useState<NativeAgentEvent[]>([])
  const [replay, setReplay] = useState<NativeAgentReplay | null>(null)
  const [decisionState, setDecisionState] = useState<NativeAgentDecisionState | null>(null)
  const [loading, setLoading] = useState(true)
  const [feedbackRating, setFeedbackRating] = useState<string | null>(null)
  const [feedbackComment, setFeedbackComment] = useState("")
  const [feedbackCorrection, setFeedbackCorrection] = useState("")
  const [submittingFeedback, setSubmittingFeedback] = useState(false)

  useEffect(() => {
    async function loadReplay() {
      try {
        const [runRes, eventsRes, replayRes, decisionStateRes] = await Promise.all([
          fetch(`/api/agent/runs/${runId}`, { cache: "no-store" }),
          fetch(`/api/agent/runs/${runId}/events`, { cache: "no-store" }),
          fetch(`/api/agent/runs/${runId}/replay`, { cache: "no-store" }),
          fetch(`/api/agent/runs/${runId}/decision-state`, { cache: "no-store" }),
        ])
        const runData = (await runRes.json()) as { data?: AgentRun } | AgentRun
        const eventsData = (await eventsRes.json()) as { data?: NativeAgentEvent[] } | NativeAgentEvent[]
        const replayData = (await replayRes.json()) as NativeAgentReplay
        const decisionStateData = (await decisionStateRes.json()) as NativeAgentDecisionState
        setRun(
          runData && typeof runData === "object" && "data" in runData
            ? runData.data || null
            : (runData as AgentRun),
        )
        setEvents(Array.isArray(eventsData) ? eventsData : eventsData.data || [])
        setReplay(replayRes.ok ? replayData : null)
        setDecisionState(decisionStateRes.ok ? decisionStateData : null)
      } catch (err) {
        toast.error("加载运行回放失败")
      } finally {
        setLoading(false)
      }
    }

    void loadReplay()
  }, [runId])

  async function submitFeedback(rating: string) {
    setFeedbackRating(rating)
    setSubmittingFeedback(true)
    try {
      const res = await fetch(`/api/agent/runs/${runId}/feedback`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          rating,
          comment: feedbackComment || undefined,
          correction: feedbackCorrection || undefined,
        }),
      })
      if (res.ok) {
        toast.success("反馈已提交")
      } else {
        toast.error("提交反馈失败")
      }
    } catch (err) {
      toast.error("提交反馈失败")
    } finally {
      setSubmittingFeedback(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <XCircle className="size-12 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">未找到运行记录</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/agent/history">返回历史</Link>
        </Button>
      </div>
    )
  }

  const statusConfig: Record<string, { icon: ElementType; label: string; className: string }> = {
    completed: {
      icon: CheckCircle2,
      label: "完成",
      className: "text-success bg-success/10 border-success/20",
    },
    running: {
      icon: Loader2,
      label: "运行中",
      className: "text-primary bg-primary/10 border-primary/20",
    },
    failed: {
      icon: XCircle,
      label: "失败",
      className: "text-destructive bg-destructive/10 border-destructive/20",
    },
    waiting_approval: {
      icon: AlertTriangle,
      label: "审批中",
      className: "text-amber-600 bg-amber-500/10 border-amber-500/20",
    },
    handoff_required: {
      icon: AlertTriangle,
      label: "交接中",
      className: "text-cyan-600 bg-cyan-500/10 border-cyan-500/20",
    },
  }

  const status = statusConfig[run.status] || statusConfig.completed
  const StatusIcon = status.icon
  const memories = extractMemories(events)

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        {/* Header */}
        <div className="mb-4">
          <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
            <Link href="/agent/history">
              <ArrowLeft className="mr-1 size-4" />
              返回
            </Link>
          </Button>

          <div className="flex items-center gap-2">
            <StatusIcon
              className={cn("size-4", run.status === "running" && "animate-spin")}
            />
            <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", status.className)}>
              {status.label}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {run.run_id.slice(0, 8)}
            </span>
          </div>

          <p className="mt-2 text-base font-medium">{run.goal}</p>

          {run.error_message && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>{run.error_message}</span>
            </div>
          )}
        </div>

        {/* Intervention controls — visible only while the run is active */}
        {(run.status === "running" || run.status === "waiting_approval" || run.status === "handoff_required") && (
          <div className="mb-4">
            <AgentInterventionPanel runId={runId} />
          </div>
        )}

        {/* Events */}
        {events.length > 0 && (
          <div className="mb-4">
            <AgentEventTimeline events={events} isRunning={run.status === "running"} />
          </div>
        )}

        {/* Replay metrics */}
        {replay?.metrics && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">回放快照</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-xs sm:grid-cols-3">
                <Metric label="运行时间" value={replay.metrics.runtime_version} />
                <Metric label="追踪" value={replay.metrics.trace_id?.slice(0, 8)} mono />
                <Metric label="审批" value={replay.metrics.approval_state} />
                <Metric label="步骤" value={replay.metrics.steps ?? replay.metrics.step_count} />
                <Metric label="工具调用" value={replay.metrics.tool_calls ?? replay.metrics.tool_call_count} />
                <Metric label="检索次数" value={replay.metrics.retrieval_count} />
                <Metric label="延迟" value={replay.metrics.latency_ms ? `${replay.metrics.latency_ms}ms` : "n/a"} />
                <Metric label="成本" value={replay.metrics.cost_estimate_usd ?? replay.metrics.cost_estimate ?? "n/a"} mono />
                <Metric label="错误" value={replay.metrics.error_count ?? 0} />
              </dl>
              {replay.summary && (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <Metric label="事件" value={replay.summary.event_count ?? 0} />
                  <Metric label="工具结果" value={replay.summary.tool_result_count ?? 0} />
                  <Metric label="审批次数" value={replay.summary.approval_count ?? 0} />
                  <Metric label="恢复次数" value={replay.summary.approval_resume_count ?? 0} />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {memories.length > 0 && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Brain className="size-4 text-emerald-500" />
                历史记忆
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {memories.slice(0, 5).map((memory, index) => (
                <div
                  key={memory.memory_id || `${memory.conclusion_type || "memory"}-${index}`}
                  className="rounded-md border border-border bg-muted/20 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium uppercase text-emerald-600">
                      {memory.conclusion_type || "memory"}
                    </span>
                    {typeof memory.confidence === "number" && (
                      <span className="text-[10px] text-muted-foreground">
                        置信度 {(memory.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                    {typeof memory.similarity === "number" && (
                      <span className="text-[10px] text-muted-foreground">
                        匹配度 {(memory.similarity * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-xs text-muted-foreground">
                    {memory.conclusion_text || "n/a"}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {decisionState && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">决策状态</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-xs sm:grid-cols-4">
                <Metric label="状态" value={decisionState.latest_status} />
                <Metric label="优先级" value={decisionState.goal?.priority} />
                <Metric
                  label="观察次数"
                  value={
                    decisionState.summary?.observation_count ??
                    decisionState.observations?.length ??
                    0
                  }
                />
                <Metric
                  label="决策次数"
                  value={
                    decisionState.summary?.decision_count ??
                    decisionState.decisions?.length ??
                    0
                  }
                />
                <Metric
                  label="证据评估"
                  value={
                    decisionState.summary?.evidence_assessment_count ??
                    decisionState.evidence_assessments?.length ??
                    0
                  }
                />
                <Metric
                  label="审批次数"
                  value={decisionState.approval_decisions?.length ?? 0}
                />
                <Metric label="恢复" value={decisionState.approval_resume?.length ?? 0} />
                <Metric
                  label="恢复事件"
                  value={
                    decisionState.summary?.recovery_count ??
                    decisionState.recovery_events?.length ??
                    0
                  }
                />
                <Metric
                  label="交接"
                  value={decisionState.handoff?.required ? decisionState.handoff.reason || "required" : "no"}
                />
              </dl>
              {decisionState.goal?.goal && (
                <p className="mt-3 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                  目标：{decisionState.goal.goal}
                </p>
              )}
              {decisionState.decisions?.at(-1)?.reasoning_summary && (
                <p className="mt-2 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                  最新决策：{decisionState.decisions.at(-1)?.reasoning_summary}
                </p>
              )}
              {decisionState.evidence_assessments?.at(-1)?.summary && (
                <p className="mt-2 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                  证据：{decisionState.evidence_assessments.at(-1)?.summary}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {replay?.tool_trajectory && replay.tool_trajectory.length > 0 && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">工具轨迹</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {replay.tool_trajectory.map((item, index) => (
                <div key={`${item.tool_name || "tool"}-${index}`} className="rounded-md border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-medium">{item.tool_name || "unknown"}</span>
                    {item.execution_status && (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
                        {item.execution_status}
                      </span>
                    )}
                    {item.approval_state && (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
                        {item.approval_state}
                      </span>
                    )}
                  </div>
                  {item.call?.message && <p className="mt-1 text-xs text-muted-foreground">{item.call.message}</p>}
                  {item.result?.message && <p className="mt-1 text-xs text-muted-foreground">{item.result.message}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {replay?.knowledge_citations && replay.knowledge_citations.length > 0 && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">知识证据</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {replay.knowledge_citations.slice(0, 6).map((citation, index) => (
                  <div
                    key={index}
                    className="rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground"
                  >
                    <pre className="whitespace-pre-wrap break-words">
                      {JSON.stringify(citation, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Report */}
        {run.final_report && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">报告</CardTitle>
            </CardHeader>
            <CardContent>
              <Markdown content={run.final_report} />
            </CardContent>
          </Card>
        )}

        {/* Feedback */}
        {run.status === "completed" && (
          <Card>
            <CardContent className="pt-4">
              {feedbackRating ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="size-4 text-success" />
                  <span>谢谢！</span>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("helpful")} disabled={submittingFeedback}>
                      <ThumbsUp className="mr-1 size-3" />
                      有帮助
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("not_helpful")} disabled={submittingFeedback}>
                      <ThumbsDown className="mr-1 size-3" />
                      没帮助
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("wrong")} disabled={submittingFeedback}>
                      <XCircle className="mr-1 size-3" />
                      有误
                    </Button>
                  </div>
                  <Textarea
                    placeholder="备注（可选）"
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    disabled={submittingFeedback}
                    className="min-h-16"
                  />
                  <Textarea
                    placeholder="正确结论或修正建议（可选，会进入 Badcase 记忆）"
                    value={feedbackCorrection}
                    onChange={(e) => setFeedbackCorrection(e.target.value)}
                    disabled={submittingFeedback}
                    className="min-h-20"
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

function extractMemories(events: NativeAgentEvent[]): NativeAgentMemory[] {
  const memories: NativeAgentMemory[] = []
  const seen = new Set<string>()
  for (const event of events) {
    if (event.type !== "memory_context") {
      continue
    }
    const payloadMemories = event.payload?.memories
    if (!Array.isArray(payloadMemories)) {
      continue
    }
    for (const memory of payloadMemories) {
      const key = memory.memory_id || `${memory.conclusion_type}:${memory.conclusion_text}`
      if (seen.has(key)) {
        continue
      }
      seen.add(key)
      memories.push(memory)
    }
  }
  return memories
}

function Metric({
  label,
  value,
  mono = false,
}: {
  label: string
  value: unknown
  mono?: boolean
}) {
  return (
    <div className="rounded-md border bg-muted/20 p-2">
      <dt className="text-[10px] uppercase text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 truncate text-sm font-medium", mono && "font-mono")}>
        {value === undefined || value === null || value === "" ? "n/a" : String(value)}
      </dd>
    </div>
  )
}
