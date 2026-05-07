"use client"

import { usePathname } from "next/navigation"
import { HealthIndicator } from "@/components/health-indicator"
import { ThemeToggle } from "@/components/theme-toggle"
import { MobileNav } from "@/components/mobile-nav"

const TITLES = [
  { path: "/agent/approvals", title: "Approvals", subtitle: "Tool approvals and resumes" },
  { path: "/agent/history", title: "History", subtitle: "Past runs and replays" },
  { path: "/agent", title: "Diagnose", subtitle: "Native agent runs and traces" },
  { path: "/chat", title: "Chat", subtitle: "Conversation and response trace" },
  { path: "/contracts", title: "API Contracts", subtitle: "OpenAPI snapshot and diff" },
  { path: "/knowledge", title: "Knowledge", subtitle: "Uploads, indexing, and documents" },
  { path: "/operations", title: "Operations", subtitle: "Runtime health and service readiness" },
  { path: "/scenarios", title: "Scenarios", subtitle: "Regression scenarios and evaluation" },
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
