"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import {
  CheckCircle2,
  Loader2,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { NativeAgentApproval } from "@/lib/native-agent-types"
import { useAgentWorkbenchStore } from "@/lib/agent-workbench-store"
import { cn } from "@/lib/utils"

export function AgentApprovalsConsole() {
  const approvals = useAgentWorkbenchStore((state) => state.approvals)
  const loading = useAgentWorkbenchStore((state) => state.approvalLoading)
  const loadApprovals = useAgentWorkbenchStore((state) => state.loadApprovals)
  const invalidateAgentData = useAgentWorkbenchStore((state) => state.invalidateAgentData)
  const [submittingKey, setSubmittingKey] = useState<string | null>(null)

  useEffect(() => {
    void loadApprovals().catch(() => toast.error("Failed to load approvals"))
  }, [loadApprovals])

  const decide = useCallback(
    async (approval: NativeAgentApproval, decision: "approved" | "rejected") => {
      const key = `${approval.run_id}:${approval.tool_name}`
      setSubmittingKey(key)
      try {
        const res = await fetch(
          `/api/agent/runs/${encodeURIComponent(approval.run_id)}/approvals/${encodeURIComponent(
            approval.tool_name,
          )}`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ decision }),
          },
        )
        if (!res.ok) {
          const json = (await res.json()) as { error?: string; detail?: string }
          throw new Error(json.error || json.detail || `HTTP ${res.status}`)
        }
        await res.json().catch(() => undefined)
        await invalidateAgentData()
        toast.success(`Approval ${decision}`)
      } catch (err) {
        toast.error((err as Error).message || "Approval update failed")
      } finally {
        setSubmittingKey(null)
      }
    },
    [invalidateAgentData],
  )

  const resume = useCallback(async (approval: NativeAgentApproval) => {
    const key = `${approval.run_id}:${approval.tool_name}:resume`
    setSubmittingKey(key)
    try {
      const res = await fetch(
        `/api/agent/runs/${encodeURIComponent(approval.run_id)}/approvals/${encodeURIComponent(
          approval.tool_name,
        )}/resume`,
        { method: "POST" },
      )
      const json = (await res.json()) as {
        status?: string
        execution_status?: string
        checkpoint_status?: string
        reason?: string
        error?: string
        detail?: string
      }
      if (!res.ok) {
        throw new Error(json.error || json.detail || json.reason || `HTTP ${res.status}`)
      }
      await invalidateAgentData()
      toast.success(`Resume ${json.status || "submitted"}`)
    } catch (err) {
      toast.error((err as Error).message || "Resume failed")
    } finally {
      setSubmittingKey(null)
    }
  }, [invalidateAgentData])

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
          <h1 className="text-2xl font-bold">Approvals</h1>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              void loadApprovals().catch(() => toast.error("Failed to load approvals"))
            }
          >
            <RefreshCw className="size-4" /> Refresh
          </Button>
        </div>

        {approvals.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <ShieldAlert className="size-10 text-muted-foreground" />
              <p className="mt-3 text-sm text-muted-foreground">No approval requests</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {approvals.map((approval) => {
              const key = `${approval.run_id}:${approval.tool_name}`
              const pending = approval.status === "pending"
              const approved = approval.status === "approved"
              return (
                <Card key={key} className={cn(!pending && "opacity-75")}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <CardTitle className="truncate text-base">
                          {approval.tool_name}
                        </CardTitle>
                        <Link
                          href={`/agent/${approval.run_id}`}
                          className="font-mono text-xs text-muted-foreground hover:text-foreground"
                        >
                          {approval.run_id.slice(0, 8)}
                        </Link>
                      </div>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          pending && "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
                          approval.status === "approved" && "bg-success/10 text-success",
                          approval.status === "rejected" && "bg-destructive/10 text-destructive",
                        )}
                      >
                        {approval.status}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {approval.goal && (
                      <p className="line-clamp-2 text-sm text-muted-foreground">
                        {approval.goal}
                      </p>
                    )}
                    <pre className="max-h-24 overflow-auto rounded-md bg-muted p-2 text-[11px]">
                      {JSON.stringify(approval.arguments || {}, null, 2)}
                    </pre>
                    {approval.resume_status && (
                      <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">
                          Resume: {approval.resume_status}
                        </span>
                        {approval.resume_checkpoint_status && (
                          <span className="ml-2">
                            checkpoint {approval.resume_checkpoint_status}
                          </span>
                        )}
                        {approval.resume_reason && (
                          <p className="mt-1 line-clamp-2">{approval.resume_reason}</p>
                        )}
                      </div>
                    )}
                    {pending && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => void decide(approval, "approved")}
                          disabled={submittingKey === key}
                        >
                          <CheckCircle2 className="size-4" /> Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void decide(approval, "rejected")}
                          disabled={submittingKey === key}
                        >
                          <XCircle className="size-4" /> Reject
                        </Button>
                      </div>
                    )}
                    {approved && approval.resume_status !== "executed" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void resume(approval)}
                        disabled={submittingKey === `${key}:resume`}
                      >
                        <PlayCircle className="size-4" /> Resume
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
