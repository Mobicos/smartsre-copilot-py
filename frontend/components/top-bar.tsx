"use client"

import { usePathname } from "next/navigation"
import { HealthIndicator } from "@/components/health-indicator"
import { ThemeToggle } from "@/components/theme-toggle"
import { MobileNav } from "@/components/mobile-nav"

const TITLES = [
  { path: "/agent/approvals", title: "审批", subtitle: "工具审批与恢复" },
  { path: "/agent/history", title: "历史记录", subtitle: "运行记录与回放" },
  { path: "/agent", title: "诊断", subtitle: "Agent 运行与追踪" },
  { path: "/chat", title: "对话", subtitle: "对话与响应追踪" },
  { path: "/contracts", title: "API 契约", subtitle: "OpenAPI 快照与差异" },
  { path: "/knowledge", title: "知识库", subtitle: "上传、索引与文档" },
  { path: "/operations", title: "运维", subtitle: "运行时健康与服务就绪" },
  { path: "/scenarios", title: "场景", subtitle: "回归场景与评估" },
] as const

export function TopBar() {
  const pathname = usePathname() ?? "/chat"
  const fallback = TITLES.find((item) => item.path === "/chat") ?? TITLES[0]
  const meta =
    TITLES.find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`)) ??
    fallback

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-background/85 px-4 py-3 backdrop-blur md:px-6">
      <MobileNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <h1 className="truncate text-sm font-semibold leading-tight md:text-base">{meta.title}</h1>
        <p className="hidden truncate text-xs text-muted-foreground sm:block">{meta.subtitle}</p>
      </div>
      <div className="flex items-center gap-2">
        <HealthIndicator />
        <ThemeToggle />
      </div>
    </header>
  )
}
