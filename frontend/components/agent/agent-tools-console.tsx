"use client"

import { useEffect } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Shield,
  ShieldAlert,
  Wrench,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { NativeTool } from "@/lib/native-agent-types"
import { useAgentWorkbenchStore } from "@/lib/agent-workbench-store"
import { cn } from "@/lib/utils"

export function AgentToolsConsole() {
  const tools = useAgentWorkbenchStore((state) => state.tools)
  const error = useAgentWorkbenchStore((state) => state.toolsError)
  const loading = useAgentWorkbenchStore((state) => state.toolsLoading)
  const loadTools = useAgentWorkbenchStore((state) => state.loadTools)

  useEffect(() => {
    void loadTools().catch(() => toast.error("Failed to load tools"))
  }, [loadTools])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Tool Registry</h1>
          <p className="text-sm text-muted-foreground">
            {tools.length} tool{tools.length !== 1 ? "s" : ""} registered
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void loadTools().catch(() => toast.error("Failed to load tools"))}
        >
          <RefreshCw className="mr-2 size-4" />
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
      ) : tools.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Wrench className="mb-4 size-8" />
            <p>No tools registered</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {tools.map((tool) => (
            <ToolCard key={tool.name} tool={tool} />
          ))}
        </div>
      )}
    </div>
  )
}

function ToolCard({ tool }: { tool: NativeTool }) {
  const riskLevel = tool.risk_level ?? tool.policy?.risk_level ?? "low"
  const approvalRequired = tool.policy?.approval_required ?? false
  const enabled = tool.policy?.enabled ?? true

  return (
    <Card className={cn(!enabled && "opacity-60")}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Wrench className="size-4 text-muted-foreground" />
            {tool.name}
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <RiskBadge level={riskLevel} />
            {approvalRequired && (
              <Badge variant="outline" className="text-xs">
                <ShieldAlert className="mr-1 size-3" />
                approval
              </Badge>
            )}
            {!enabled && (
              <Badge variant="secondary" className="text-xs">
                disabled
              </Badge>
            )}
          </div>
        </div>
        <CardDescription className="line-clamp-2">
          {tool.description || "No description"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-muted-foreground">
        {tool.owner && (
          <div className="flex items-center gap-1.5">
            <Shield className="size-3" />
            <span>Owner: {tool.owner}</span>
          </div>
        )}
        {tool.allowed_scopes && tool.allowed_scopes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tool.allowed_scopes.map((scope) => (
              <Badge key={scope} variant="secondary" className="text-[10px]">
                {scope}
              </Badge>
            ))}
          </div>
        )}
        {tool.schema && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-foreground/70 hover:text-foreground">
              Schema
            </summary>
            <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted p-2 text-[10px]">
              {JSON.stringify(tool.schema, null, 2)}
            </pre>
          </details>
        )}
      </CardContent>
    </Card>
  )
}

function RiskBadge({ level }: { level: string }) {
  const config: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; icon: typeof AlertTriangle }> = {
    high: { variant: "destructive", icon: ShieldAlert },
    medium: { variant: "outline", icon: AlertTriangle },
    low: { variant: "secondary", icon: CheckCircle2 },
  }
  const { variant, icon: Icon } = config[level] ?? config.low
  return (
    <Badge variant={variant} className="text-xs">
      <Icon className="mr-1 size-3" />
      {level}
    </Badge>
  )
}
