"use client"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { StatusDot } from "@/components/status-dot"
import { useHealth } from "@/lib/use-health"
import { cn } from "@/lib/utils"

type Tone = "ok" | "warn" | "error" | "muted"

function pickTone(status: unknown): Tone {
  if (status == null) return "muted"
  if (typeof status === "string") {
    const value = status.toLowerCase()
    if (value.includes("ok") || value.includes("up") || value.includes("healthy") || value === "connected") {
      return "ok"
    }
    if (value.includes("degrad") || value.includes("warn") || value === "configured") {
      return "warn"
    }
    if (value.includes("down") || value.includes("error") || value.includes("fail")) {
      return "error"
    }
    return "muted"
  }
  if (typeof status === "object" && status && "status" in status) {
    return pickTone((status as { status: unknown }).status)
  }
  return "muted"
}

export function HealthIndicator() {
  const { data, loading } = useHealth()
  const status = data?.payload?.status ?? (data?.ok ? "healthy" : "unhealthy")
  const tone: Tone = !data ? "muted" : !data.ok ? "error" : pickTone(status)
  const label = tone === "ok" ? "健康" : tone === "warn" ? "降级" : tone === "error" ? "宕机" : "未知"

  const services: Array<{ key: string; tone: Tone; label: string; detail: string }> = []
  const payload = data?.payload
  if (payload) {
    if ("milvus" in payload) {
      const value = payload.milvus
      services.push({
        key: "milvus",
        tone: pickTone(value),
        label: "Milvus",
        detail: typeof value === "string" ? value : JSON.stringify(value),
      })
    }
    if ("redis" in payload) {
      services.push({
        key: "redis",
        tone: pickTone(payload.redis),
        label: "Redis",
        detail: typeof payload.redis === "object" && payload.redis !== null
          ? (payload.redis.message || payload.redis.status || JSON.stringify(payload.redis))
          : String(payload.redis),
      })
    }
    if ("decision_runtime" in payload && payload.decision_runtime) {
      const runtime = payload.decision_runtime
      services.push({
        key: "decision-runtime",
        tone: pickTone(runtime.status),
        label: "Decision Runtime",
        detail:
          runtime.message ||
          (runtime.detail ? JSON.stringify(runtime.detail) : String(runtime.status ?? "unknown")),
      })
    }
    if (payload.mcp && typeof payload.mcp === "object") {
      for (const [name, value] of Object.entries(payload.mcp)) {
        services.push({
          key: `mcp-${name}`,
          tone: pickTone(value),
          label: `MCP ${name}`,
          detail: String(value),
        })
      }
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs font-medium transition-colors",
            "hover:bg-accent hover:text-accent-foreground",
          )}
          aria-label={`System health: ${label}`}
        >
          <StatusDot tone={tone} pulse={tone === "ok" || loading} />
          <span className="hidden sm:inline">{loading ? "检测中" : label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <div className="border-b border-border px-3 py-2.5">
          <p className="text-sm font-medium">系统健康</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {loading ? "正在检测服务状态" : data?.error ? `无法连接：${data.error}` : "实时服务状态"}
          </p>
        </div>
        <ul className="p-2">
          {services.length === 0 ? (
            <li className="px-2 py-1.5 text-xs text-muted-foreground">
              {loading ? "加载详情中..." : "暂无组件详情"}
            </li>
          ) : (
            services.map((service) => (
              <li
                key={service.key}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
              >
                <span className="flex items-center gap-2">
                  <StatusDot tone={service.tone} />
                  <span className="font-medium">{service.label}</span>
                </span>
                <span className="max-w-[140px] truncate text-muted-foreground" title={service.detail}>
                  {service.detail}
                </span>
              </li>
            ))
          )}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
