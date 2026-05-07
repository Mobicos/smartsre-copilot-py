"use client"

import type { ElementType } from "react"
import { useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowLeft,
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
import { cn } from "@/lib/utils"
import type {
  NativeAgentDecisionState,
  NativeAgentEvent,
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
        toast.error("Failed to load run replay")
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
        body: JSON.stringify({ rating, comment: feedbackComment || undefined }),
      })
      if (res.ok) {
        toast.success("Feedback submitted")
      } else {
        toast.error("Failed to submit feedback")
      }
    } catch (err) {
      toast.error("Failed to submit feedback")
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
        <p className="text-sm text-muted-foreground">Run not found</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/agent/history">Back to History</Link>
        </Button>
      </div>
    )
  }

  const statusConfig: Record<string, { icon: ElementType; label: string; className: string }> = {
    completed: {
      icon: CheckCircle2,
      label: "Done",
      className: "text-success bg-success/10 border-success/20",
    },
    running: {
      icon: Loader2,
      label: "Running",
      className: "text-primary bg-primary/10 border-primary/20",
    },
    failed: {
      icon: XCircle,
      label: "Failed",
      className: "text-destructive bg-destructive/10 border-destructive/20",
    },
  }

  const status = statusConfig[run.status] || statusConfig.completed
  const StatusIcon = status.icon

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        {/* Header */}
        <div className="mb-4">
          <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
            <Link href="/agent/history">
              <ArrowLeft className="mr-1 size-4" />
              Back
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
              <CardTitle className="text-base">Replay Snapshot</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-xs sm:grid-cols-3">
                <Metric label="Runtime" value={replay.metrics.runtime_version} />
                <Metric label="Trace" value={replay.metrics.trace_id?.slice(0, 8)} mono />
                <Metric label="Approval" value={replay.metrics.approval_state} />
                <Metric label="Steps" value={replay.metrics.steps ?? replay.metrics.step_count} />
                <Metric label="Tool Calls" value={replay.metrics.tool_calls ?? replay.metrics.tool_call_count} />
                <Metric label="Retrievals" value={replay.metrics.retrieval_count} />
                <Metric label="Latency" value={replay.metrics.latency_ms ? `${replay.metrics.latency_ms}ms` : "n/a"} />
                <Metric label="Cost" value={replay.metrics.cost_estimate_usd ?? replay.metrics.cost_estimate ?? "n/a"} mono />
                <Metric label="Errors" value={replay.metrics.error_count ?? 0} />
              </dl>
              {replay.summary && (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <Metric label="Events" value={replay.summary.event_count ?? 0} />
                  <Metric label="Tool Results" value={replay.summary.tool_result_count ?? 0} />
                  <Metric label="Approvals" value={replay.summary.approval_count ?? 0} />
                  <Metric label="Resumes" value={replay.summary.approval_resume_count ?? 0} />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {decisionState && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Decision State</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-xs sm:grid-cols-4">
                <Metric label="Status" value={decisionState.latest_status} />
                <Metric label="Decisions" value={decisionState.decisions?.length ?? 0} />
                <Metric
                  label="Approvals"
                  value={decisionState.approval_decisions?.length ?? 0}
                />
                <Metric label="Resume" value={decisionState.approval_resume?.length ?? 0} />
                <Metric label="Recovery" value={decisionState.recovery_events?.length ?? 0} />
              </dl>
              {decisionState.decisions?.at(-1)?.message && (
                <p className="mt-3 rounded-md bg-muted p-2 text-xs text-muted-foreground">
                  {decisionState.decisions.at(-1)?.message}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {replay?.tool_trajectory && replay.tool_trajectory.length > 0 && (
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Tool Trajectory</CardTitle>
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
              <CardTitle className="text-base">Knowledge Evidence</CardTitle>
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
              <CardTitle className="text-base">Report</CardTitle>
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
                  <span>Thanks!</span>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("helpful")} disabled={submittingFeedback}>
                      <ThumbsUp className="mr-1 size-3" />
                      Helpful
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("not_helpful")} disabled={submittingFeedback}>
                      <ThumbsDown className="mr-1 size-3" />
                      Not Helpful
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => submitFeedback("wrong")} disabled={submittingFeedback}>
                      <XCircle className="mr-1 size-3" />
                      Wrong
                    </Button>
                  </div>
                  <Textarea
                    placeholder="Comment (optional)"
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    disabled={submittingFeedback}
                    className="min-h-16"
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
