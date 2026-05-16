"use client"

import { useCallback, useState } from "react"
import { AlertCircle, ArrowRight, Eye, PenTool, Send } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import type {
  NativeAgentInterventionRequest,
  NativeAgentInterventionResponse,
} from "@/lib/native-agent-types"
import { cn } from "@/lib/utils"

type InterventionType = NativeAgentInterventionRequest["intervention_type"]

interface InterventionConfig {
  type: InterventionType
  label: string
  icon: typeof Eye
  description: string
  placeholder: string
  payloadBuilder: (text: string) => Record<string, unknown>
}

const INTERVENTION_TYPES: InterventionConfig[] = [
  {
    type: "inject_evidence",
    label: "注入证据",
    icon: Eye,
    description: "在下一次决策前追加观察数据",
    placeholder: "输入要注入的证据内容，例如：\n\"内存占用已恢复到 60%，GC 日志显示 full GC 频率正常\"",
    payloadBuilder: (text) => ({ evidence: text }),
  },
  {
    type: "replace_tool_call",
    label: "替换工具调用",
    icon: PenTool,
    description: "覆盖当前待执行的工具调用决策",
    placeholder: "输入替换的工具名称和参数（JSON 格式），例如：\n{\"tool\": \"restart_service\", \"args\": {\"service\": \"order-service\"}}",
    payloadBuilder: (text) => {
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>
        return { tool_name: parsed.tool, tool_arguments: parsed.args ?? {} }
      } catch {
        return { raw: text }
      }
    },
  },
  {
    type: "modify_goal",
    label: "修改目标",
    icon: ArrowRight,
    description: "更新当前运行的目标合同",
    placeholder: "输入新的目标描述，例如：\n\"优先排查 order-service 的内存泄漏，暂不处理 CPU 告警\"",
    payloadBuilder: (text) => ({ goal: text }),
  },
]

interface AgentInterventionPanelProps {
  runId: string
  className?: string
}

export function AgentInterventionPanel({ runId, className }: AgentInterventionPanelProps) {
  const [selectedType, setSelectedType] = useState<InterventionType | null>(null)
  const [payloadText, setPayloadText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [lastResponse, setLastResponse] = useState<NativeAgentInterventionResponse | null>(null)

  const activeConfig = INTERVENTION_TYPES.find((c) => c.type === selectedType)

  const submit = useCallback(async () => {
    if (!activeConfig || !payloadText.trim()) return
    setSubmitting(true)
    try {
      const res = await fetch(`/api/agent/runs/${encodeURIComponent(runId)}/intervene`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          intervention_type: activeConfig.type,
          payload: activeConfig.payloadBuilder(payloadText),
        }),
      })
      const json = (await res.json()) as {
        data?: NativeAgentInterventionResponse
        error?: string
        detail?: string
        message?: string
      }
      if (!res.ok) {
        throw new Error(json.error || json.detail || json.message || `HTTP ${res.status}`)
      }
      const data = json.data ?? (json as unknown as NativeAgentInterventionResponse)
      setLastResponse(data)
      toast.success(`已提交：${activeConfig.label}`)
      setPayloadText("")
      setTimeout(() => setLastResponse(null), 3000)
    } catch (err) {
      toast.error((err as Error).message || "干预提交失败")
    } finally {
      setSubmitting(false)
    }
  }, [activeConfig, payloadText, runId])

  return (
    <Card className={cn("border-cyan-200 bg-cyan-50/30 dark:border-cyan-800 dark:bg-cyan-950/20", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base text-cyan-700 dark:text-cyan-300">
          <AlertCircle className="size-4" />
          人工干预
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {INTERVENTION_TYPES.map((config) => {
            const Icon = config.icon
            return (
              <Button
                key={config.type}
                size="sm"
                variant={selectedType === config.type ? "default" : "outline"}
                onClick={() => {
                  setSelectedType(selectedType === config.type ? null : config.type)
                  setPayloadText("")
                }}
                className="gap-1.5"
              >
                <Icon className="size-3.5" />
                {config.label}
              </Button>
            )
          })}
        </div>

        {activeConfig && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">{activeConfig.description}</p>
            <Textarea
              placeholder={activeConfig.placeholder}
              value={payloadText}
              onChange={(e) => setPayloadText(e.target.value)}
              disabled={submitting}
              className="min-h-24 font-mono text-xs"
            />
            <div className="flex items-center justify-between">
              {lastResponse && (
                <span className="text-xs text-success">
                  {lastResponse.intervention_id}
                </span>
              )}
              <Button
                size="sm"
                onClick={() => void submit()}
                disabled={submitting || !payloadText.trim()}
                className="ml-auto gap-1.5"
              >
                <Send className="size-3.5" />
                {submitting ? "提交中..." : "提交干预"}
              </Button>
            </div>
          </div>
        )}

        {!activeConfig && !lastResponse && (
          <p className="text-xs text-muted-foreground">
            选择干预类型，可在运行中注入证据、替换工具调用或修改目标
          </p>
        )}
      </CardContent>
    </Card>
  )
}
