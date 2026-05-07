"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Activity, Database, Loader2, RefreshCw, ServerCog } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface HealthResponse {
  ok: boolean
  status: number
  payload?: {
    status?: string
    service?: string
    version?: string
    database?: HealthItem
    vector_backend?: HealthItem & { backend?: string }
    embedding?: HealthItem
    vector_store?: HealthItem
    object_storage?: HealthItem
    decision_runtime?: HealthItem & { detail?: Record<string, unknown> }
    task_dispatcher?: HealthItem
    agent_resume_dispatcher?: HealthItem & { queue?: string }
    indexing_tasks?: {
      status?: string
      counts?: Record<string, number>
      message?: string
    }
    redis?: HealthItem
    error?: string
    warning?: string
    [key: string]: unknown
  }
  error?: string
}

interface HealthItem {
  status?: string
  message?: string
}

export function OperationsConsole() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const loadHealth = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/health", { cache: "no-store" })
      const data = (await res.json()) as HealthResponse
      setHealth(data)
      if (!data.ok) {
        toast.warning(data.payload?.error || data.error || "Health check is not green")
      }
    } catch (err) {
      toast.error((err as Error).message || "Health check failed")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHealth()
  }, [loadHealth])

  const payload = health?.payload
  const services = useMemo(
    () => [
      {
        name: "Database",
        status: payload?.database?.status,
        message: payload?.database?.message,
        icon: Database,
      },
      {
        name: "Vector Backend",
        status: payload?.vector_backend?.status,
        message: payload?.vector_backend?.backend,
        icon: ServerCog,
      },
      {
        name: "Embedding",
        status: payload?.embedding?.status,
        message: payload?.embedding?.message,
        icon: Activity,
      },
      {
        name: "Vector Store",
        status: payload?.vector_store?.status,
        message: payload?.vector_store?.message,
        icon: ServerCog,
      },
        {
          name: "Object Storage",
          status: payload?.object_storage?.status,
          message: payload?.object_storage?.message,
          icon: ServerCog,
        },
        {
          name: "Decision Runtime",
          status: payload?.decision_runtime?.status,
          message: payload?.decision_runtime?.message,
          icon: Activity,
        },
        {
          name: "Task Dispatcher",
          status: payload?.task_dispatcher?.status,
          message: payload?.task_dispatcher?.message,
          icon: Activity,
      },
      {
        name: "Approval Resume",
        status: payload?.agent_resume_dispatcher?.status,
        message: payload?.agent_resume_dispatcher?.queue,
        icon: Activity,
      },
      {
        name: "Redis",
        status: payload?.redis?.status || "not_configured",
        message: payload?.redis?.message,
        icon: Database,
      },
    ],
    [payload],
  )

  if (loading && !health) {
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
          <div>
            <h1 className="text-2xl font-bold">Operations</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {payload?.service || "SmartSRE"} {payload?.version}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void loadHealth()}>
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            Refresh
          </Button>
        </div>

        <div className="mb-4 rounded-md border border-border bg-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm text-muted-foreground">Readiness</p>
              <p className="mt-1 text-lg font-semibold">{payload?.status || "unknown"}</p>
            </div>
            <StatusBadge status={payload?.status || (health?.ok ? "healthy" : "unhealthy")} />
          </div>
          {payload?.warning && (
            <p className="mt-3 rounded-md bg-amber-100 px-3 py-2 text-sm text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              {payload.warning}
            </p>
          )}
          {payload?.error && (
            <p className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {payload.error}
            </p>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {services.map((service) => {
            const Icon = service.icon
            return (
              <Card key={service.name}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Icon className="size-4 text-muted-foreground" />
                    {service.name}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <StatusBadge status={service.status || "unknown"} />
                  {service.message && (
                    <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
                      {service.message}
                    </p>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>

        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">Indexing Tasks</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(payload?.indexing_tasks?.counts || {}).map(([status, count]) => (
                <div key={status} className="rounded-md border border-border px-3 py-2">
                  <p className="font-mono text-sm font-semibold">{count}</p>
                  <p className="text-xs text-muted-foreground">{status}</p>
                </div>
              ))}
              {Object.keys(payload?.indexing_tasks?.counts || {}).length === 0 && (
                <p className="text-sm text-muted-foreground">No indexing task counts available</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase()
  const good = ["healthy", "connected", "ready", "running", "idle", "configured"].includes(
    normalized,
  )
  const warning = [
    "degraded",
    "external",
    "not_initialized",
    "not_configured",
  ].includes(normalized)
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
        good && "bg-success/10 text-success",
        warning && "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
        !good && !warning && "bg-destructive/10 text-destructive",
      )}
    >
      {status}
    </span>
  )
}
