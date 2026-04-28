"use client"

import { usePathname } from "next/navigation"
import { HealthIndicator } from "@/components/health-indicator"
import { ThemeToggle } from "@/components/theme-toggle"
import { MobileNav } from "@/components/mobile-nav"

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/chat": { title: "问答台", subtitle: "把问题说出来，它会查阅资料后回答你" },
  "/diagnose": { title: "故障诊断", subtitle: "描述现象，它会一步步排查并给你结论" },
  "/knowledge": { title: "知识库", subtitle: "上传你们的运维资料，让它读懂你们的系统" },
  "/health": { title: "运行状态", subtitle: "实时检测它是否还在正常工作" },
  "/settings": { title: "设置", subtitle: "调整外观与连接方式" },
}

export function TopBar() {
  const pathname = usePathname() ?? "/chat"
  const key = Object.keys(TITLES).find((k) => pathname.startsWith(k)) ?? "/chat"
  const meta = TITLES[key]

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-background/85 px-4 py-3 backdrop-blur md:px-6">
      <MobileNav />
      <div className="flex flex-col min-w-0 flex-1">
        <h1 className="text-sm font-semibold leading-tight md:text-base truncate">
          {meta.title}
        </h1>
        <p className="hidden sm:block text-xs text-muted-foreground truncate">{meta.subtitle}</p>
      </div>
      <div className="flex items-center gap-2">
        <HealthIndicator />
        <ThemeToggle />
      </div>
    </header>
  )
}
