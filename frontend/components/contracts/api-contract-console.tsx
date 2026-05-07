"use client"

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { FileText, Loader2, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

interface ApiOperation {
  path: string
  method: string
  operation_id?: string | null
  summary?: string | null
  tags: string[]
  fingerprint: string
}

interface ApiOperationChange {
  path: string
  method: string
  operation_id?: string | null
  current: ApiOperation
  previous: ApiOperation
}

interface ApiSpecSummary {
  title?: string | null
  version?: string | null
  path_count: number
  operation_count: number
  tags: string[]
}

interface ApiContractDiff {
  status: string
  added_count: number
  removed_count: number
  changed_count: number
  added_operations: ApiOperation[]
  removed_operations: ApiOperation[]
  changed_operations: ApiOperationChange[]
}

interface ApiContractPayload {
  snapshot_path: string
  snapshot_exists: boolean
  current: ApiSpecSummary
  snapshot: ApiSpecSummary | null
  diff: ApiContractDiff
  current_spec?: unknown
  snapshot_spec?: unknown
}

export function ApiContractConsole() {
  const [contract, setContract] = useState<ApiContractPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [includeSpec, setIncludeSpec] = useState(false)

  const loadContract = useCallback(async (showSpec = includeSpec) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/contracts/openapi?include_spec=${showSpec ? "true" : "false"}`, {
        cache: "no-store",
      })
      const data = (await res.json()) as ApiContractPayload & {
        error?: string
        detail?: string
      }
      if (!res.ok) {
        throw new Error(data.error || data.detail || `HTTP ${res.status}`)
      }
      setContract(data)
    } catch (err) {
      toast.error((err as Error).message || "Failed to load contract snapshot")
    } finally {
      setLoading(false)
    }
  }, [includeSpec])

  useEffect(() => {
    void loadContract()
  }, [loadContract])

  const diff = contract?.diff
  const current = contract?.current

  const counts = useMemo(
    () => [
      { label: "Added", value: diff?.added_count ?? 0, tone: "text-success" },
      { label: "Removed", value: diff?.removed_count ?? 0, tone: "text-destructive" },
      { label: "Changed", value: diff?.changed_count ?? 0, tone: "text-amber-600 dark:text-amber-400" },
    ],
    [diff],
  )

  if (loading && !contract) {
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
          <div className="min-w-0">
            <h1 className="text-2xl font-bold">API Contracts</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Compare the live OpenAPI document against the committed snapshot.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
              <Switch
                checked={includeSpec}
                onCheckedChange={setIncludeSpec}
                aria-label="Include raw OpenAPI spec"
              />
              <span className="text-sm text-muted-foreground">Include spec</span>
            </div>
            <Button variant="outline" size="sm" onClick={() => void loadContract(includeSpec)}>
              {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
              Refresh
            </Button>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Snapshot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-muted-foreground">Exists</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    contract?.snapshot_exists
                      ? "bg-success/10 text-success"
                      : "bg-destructive/10 text-destructive",
                  )}
                >
                  {contract?.snapshot_exists ? "yes" : "missing"}
                </span>
              </div>
              <p className="break-all font-mono text-xs text-muted-foreground">
                {contract?.snapshot_path}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Current Spec</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm font-medium">{current?.title || "Unknown title"}</p>
              <p className="text-xs text-muted-foreground">
                Version {current?.version || "n/a"} with {current?.operation_count ?? 0} operations
              </p>
              <p className="text-xs text-muted-foreground">
                {current?.path_count ?? 0} paths and {current?.tags?.length ?? 0} tags
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Diff Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-muted-foreground">State</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    diff?.status === "synced"
                      ? "bg-success/10 text-success"
                      : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
                  )}
                >
                  {diff?.status || "unknown"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {counts.map((item) => (
                  <div key={item.label} className="rounded-md border border-border p-2">
                    <p className={cn("font-mono text-sm font-semibold", item.tone)}>{item.value}</p>
                    <p className="text-[11px] text-muted-foreground">{item.label}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <OperationPanel
            title="Added operations"
            icon={<FileText className="size-4 text-success" />}
            items={diff?.added_operations || []}
            emptyLabel="No additions"
          />
          <OperationPanel
            title="Removed operations"
            icon={<FileText className="size-4 text-destructive" />}
            items={diff?.removed_operations || []}
            emptyLabel="No removals"
          />
          <OperationPanel
            title="Changed operations"
            icon={<FileText className="size-4 text-amber-600 dark:text-amber-400" />}
            items={diff?.changed_operations || []}
            emptyLabel="No changes"
            renderItem={(item) => (
              <div className="space-y-2">
                <OperationLine operation={item.current} />
                <p className="text-xs text-muted-foreground">
                  Previous: {item.previous.summary || item.previous.operation_id || "n/a"}
                </p>
              </div>
            )}
          />
        </div>

        {includeSpec && (
          <div className="mt-6 grid gap-4 xl:grid-cols-2">
            <SpecBlock title="Current OpenAPI" spec={contract?.current_spec} />
            <SpecBlock title="Snapshot OpenAPI" spec={contract?.snapshot_spec} />
          </div>
        )}
      </div>
    </div>
  )
}

function OperationPanel({
  title,
  icon,
  items,
  emptyLabel,
  renderItem,
}: {
  title: string
  icon: ReactNode
  items: ApiOperation[] | ApiOperationChange[]
  emptyLabel: string
  renderItem?: (item: ApiOperationChange) => ReactNode
}) {
  return (
    <Card className="min-h-[220px]">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyLabel}</p>
        ) : (
          items.map((item) => (
            <div key={`${item.method} ${item.path}`} className="rounded-md border border-border p-3">
              {"current" in item && renderItem ? renderItem(item) : <OperationLine operation={item as ApiOperation} />}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}

function OperationLine({ operation }: { operation: ApiOperation }) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[11px] font-semibold">
          {operation.method}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{operation.path}</span>
      </div>
      <p className="text-sm font-medium">{operation.summary || operation.operation_id || "Untitled"}</p>
      {operation.tags.length > 0 && (
        <p className="text-xs text-muted-foreground">Tags: {operation.tags.join(", ")}</p>
      )}
    </div>
  )
}

function SpecBlock({ title, spec }: { title: string; spec: unknown }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="max-h-80 overflow-auto rounded-md bg-muted/50 p-3 font-mono text-[11px] leading-5">
          {JSON.stringify(spec ?? null, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}
