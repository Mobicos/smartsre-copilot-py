"use client"

import type { ElementType } from "react"
import { useEffect } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useAgentWorkbenchStore } from "@/lib/agent-workbench-store"
import { cn } from "@/lib/utils"

const STATUS_CONFIG: Record<string, { icon: ElementType; label: string; className: string }> = {
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
  waiting_approval: {
    icon: AlertTriangle,
    label: "Approval",
    className: "text-amber-600 bg-amber-500/10 border-amber-500/20",
  },
  handoff_required: {
    icon: AlertTriangle,
    label: "Handoff",
    className: "text-cyan-600 bg-cyan-500/10 border-cyan-500/20",
  },
}

export function AgentHistoryList() {
  const runs = useAgentWorkbenchStore((state) => state.runs)
  const error = useAgentWorkbenchStore((state) => state.runsError)
  const loading = useAgentWorkbenchStore((state) => state.runsLoading)
  const loadRuns = useAgentWorkbenchStore((state) => state.loadRuns)

  useEffect(() => {
    void loadRuns().catch(() => toast.error("Failed to load history"))
  }, [loadRuns])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">History</h1>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadRuns().catch(() => toast.error("Failed to load history"))}
          >
            Refresh
          </Button>
        </div>

        {error ? (
          <Card className="border-destructive/30">
            <CardContent className="flex items-center gap-3 py-6 text-sm text-destructive">
              <AlertTriangle className="size-5" />
              {error}
            </CardContent>
          </Card>
        ) : runs.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <p className="text-sm text-muted-foreground">No runs yet</p>
              <Button asChild className="mt-4" size="sm">
                <Link href="/agent">Start Diagnosis</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => {
              const runStatus = run.status || "completed"
              const statusConfig = STATUS_CONFIG[runStatus] || STATUS_CONFIG.completed
              const StatusIcon = statusConfig.icon

              return (
                <Link key={run.run_id} href={`/agent/${run.run_id}`}>
                  <Card className="transition-colors hover:bg-muted/50">
                    <CardContent className="flex items-start gap-3 p-3">
                      <StatusIcon
                        className={cn(
                          "mt-0.5 size-4 shrink-0",
                          runStatus === "running" && "animate-spin",
                          statusConfig.className.split(" ")[0],
                        )}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium line-clamp-1">
                          {run.goal}
                        </p>
                        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <span
                            className={cn(
                              "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                              statusConfig.className,
                            )}
                          >
                            {statusConfig.label}
                          </span>
                          {run.created_at && (
                            <span className="flex items-center gap-1">
                              <Clock className="size-3" />
                              {formatDate(run.created_at)}
                            </span>
                          )}
                          {run.runtime_version && <span>{run.runtime_version}</span>}
                          {run.trace_id && (
                            <span className="font-mono">{run.trace_id.slice(0, 8)}</span>
                          )}
                          {run.approval_state && <span>{run.approval_state}</span>}
                        </div>
                        {run.error_message && (
                          <p className="mt-1 flex items-center gap-1 text-xs text-destructive">
                            <AlertTriangle className="size-3" />
                            {run.error_message}
                          </p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function formatDate(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return timestamp
  }
}
