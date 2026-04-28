"use client"

import { useHealth } from "@/lib/use-health"
import { StatusDot } from "@/components/status-dot"
import { Button } from "@/components/ui/button"
import { RefreshCw } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"

function tone(value: unknown): "ok" | "warn" | "error" | "muted" {
  if (value == null) return "muted"
  if (typeof value === "string") {
    const v = value.toLowerCase()
    if (v.includes("ok") || v.includes("up") || v.includes("healthy") || v === "connected") return "ok"
    if (v.includes("warn") || v.includes("degrad")) return "warn"
    if (v.includes("down") || v.includes("error") || v.includes("fail")) return "error"
  }
  if (typeof value === "object" && value && "status" in value) {
    return tone((value as { status: unknown }).status)
  }
  return "muted"
}

// Friendly aliases for known subsystems.
const FRIENDLY: Record<string, string> = {
  milvus: "知识检索",
  redis: "缓存",
  database: "数据库",
  llm: "大模型连接",
  mcp: "外部工具",
}

function friendlyName(key: string): string {
  const lower = key.toLowerCase()
  for (const [k, v] of Object.entries(FRIENDLY)) {
    if (lower.includes(k)) return v
  }
  return key
}

function describe(value: unknown, healthy: boolean): string {
  if (healthy) return "工作正常"
  if (typeof value === "string") return value
  if (value && typeof value === "object" && "status" in value) {
    return String((value as { status: unknown }).status)
  }
  return "状态未知"
}

export default function HealthPage() {
  const { data, loading } = useHealth(10000)

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-3xl px-4 py-6 md:px-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">它现在好不好？</h2>
            <p className="text-xs text-muted-foreground">
              每隔 10 秒自动检查一次
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => location.reload()}
            aria-label="刷新"
          >
            <RefreshCw className="size-3.5" /> 立刻再查一次
          </Button>
        </div>

        {loading || !data ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-center gap-3">
                <StatusDot tone={data.ok ? "ok" : "error"} pulse />
                <div className="flex-1">
                  <p className="text-sm font-medium">
                    {data.ok ? "一切正常，可以放心用" : "它现在没法工作"}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {data.ok
                      ? "如果回答变慢或诊断卡住，再回到这里看看。"
                      : data.error
                        ? `连不上后端：${data.error}`
                        : "后端没有正确响应，请联系系统管理员。"}
                  </p>
                </div>
              </div>
            </div>

            {data.payload && Object.keys(data.payload).length > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground">
                  它依赖的几样东西
                </h3>
                <ul className="space-y-2">
                  {Object.entries(data.payload).map(([key, value]) => {
                    const t = tone(value)
                    return (
                      <li
                        key={key}
                        className="flex items-start justify-between gap-3 rounded-md border border-border bg-card px-4 py-3"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <StatusDot tone={t} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium">{friendlyName(key)}</p>
                            <p className="text-xs text-muted-foreground truncate">
                              {describe(value, t === "ok")}
                            </p>
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}
