"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Activity, Bot, BookOpen, MessageSquare, Settings, Stethoscope, Terminal } from "lucide-react"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/chat", label: "问答台", icon: MessageSquare, desc: "把问题说出来，得到答案" },
  { href: "/diagnose", label: "故障诊断", icon: Stethoscope, desc: "把现象交给它，看它怎么查" },
  { href: "/agent", label: "Agent Harness", icon: Bot, desc: "运行场景、工具与 Agent 历史" },
  { href: "/knowledge", label: "知识库", icon: BookOpen, desc: "让它读懂你们的资料" },
  { href: "/health", label: "运行状态", icon: Activity, desc: "看一眼它今天好不好" },
  { href: "/settings", label: "设置", icon: Settings, desc: "调整工作方式" },
]

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <aside
      className="hidden md:flex md:w-64 lg:w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
      aria-label="主导航"
    >
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-sidebar-border">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Terminal className="size-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-tight">SmartSRE Copilot</span>
          <span className="text-xs text-muted-foreground leading-tight">你的运维副驾</span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        <ul className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(`${item.href}/`)
            const Icon = item.icon
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "group flex items-start gap-3 rounded-md px-3 py-2.5 transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                  )}
                >
                  <Icon
                    className={cn(
                      "size-4 mt-0.5 shrink-0 transition-colors",
                      active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                    )}
                  />
                  <span className="flex flex-col leading-tight">
                    <span className="text-sm font-medium">{item.label}</span>
                    <span className="text-[11px] text-muted-foreground">{item.desc}</span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <p className="text-xs text-muted-foreground leading-relaxed text-pretty">
          凌晨三点告警群在响时，
          <br />
          它陪你一起把问题搞清楚。
        </p>
      </div>
    </aside>
  )
}
