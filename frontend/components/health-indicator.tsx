"use client"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { StatusDot } from "@/components/status-dot"
import { useHealth } from "@/lib/use-health"
import { cn } from "@/lib/utils"

function pickTone(status: unknown): "ok" | "warn" | "error" | "muted" {
  if (status == null) return "muted"
  if (typeof status === "string") {
    const s = status.toLowerCase()
    if (s.includes("ok") || s.includes("up") || s.includes("healthy") || s === "connected") return "ok"
    if (s.includes("degrad") || s.includes("warn")) return "warn"
    if (s.includes("down") || s.includes("error") || s.includes("fail")) return "error"
    return "muted"
  }
  if (typeof status === "object" && status && "status" in status) {
    return pickTone((status as { status: unknown }).status)
  }
  return "muted"
}

export function HealthIndicator() {
  const { data, loading } = useHealth()
  const top: "ok" | "warn" | "error" | "muted" = !data
    ? "muted"
    : !data.ok
      ? "error"
      : pickTone(data.payload?.status ?? "ok")

  const label =
    top === "ok" ? "运行正常" : top === "warn" ? "状态不太好" : top === "error" ? "连不上" : "—"

  const subs: Array<{ key: string; tone: ReturnType<typeof pickTone>; label: string; detail: string }> = []
  if (data?.payload) {
    const p = data.payload
    if ("milvus" in p) {
      const v = p.milvus
      subs.push({
        key: "milvus",
        tone: pickTone(v),
        label: "Milvus",
        detail: typeof v === "string" ? v : JSON.stringify(v),
      })
    }
    if ("redis" in p) {
      subs.push({
        key: "redis",
        tone: pickTone(p.redis),
        label: "Redis",
        detail: String(p.redis),
      })
    }
    if (p.mcp && typeof p.mcp === "object") {
      for (const [k, v] of Object.entries(p.mcp)) {
        subs.push({ key: `mcp-${k}`, tone: pickTone(v), label: `MCP · ${k}`, detail: String(v) })
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
          aria-label={`系统状态：${label}`}
        >
          <StatusDot tone={top} pulse={top === "ok" || loading} />
          <span className="hidden sm:inline">{loading ? "检测中" : label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <div className="border-b border-border px-3 py-2.5">
          <p className="text-sm font-medium">它现在好不好？</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {loading
              ? "刚问过它…"
              : data?.ok
                ? "刚才检查过，一切正常"
                : data?.error
                  ? `连不上：${data.error}`
                  : "状态有点不对劲"}
          </p>
        </div>
        <ul className="p-2">
          {subs.length === 0 ? (
            <li className="px-2 py-1.5 text-xs text-muted-foreground">
              {loading ? "正在打听…" : "没拿到更详细的信息"}
            </li>
          ) : (
            subs.map((s) => (
              <li
                key={s.key}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
              >
                <span className="flex items-center gap-2">
                  <StatusDot tone={s.tone} />
                  <span className="font-medium">{s.label}</span>
                </span>
                <span className="text-muted-foreground truncate max-w-[140px]" title={s.detail}>
                  {s.detail}
                </span>
              </li>
            ))
          )}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
