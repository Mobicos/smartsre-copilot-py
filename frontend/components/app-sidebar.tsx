"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  BookOpen,
  FileText,
  History,
  MessageSquare,
  ServerCog,
  Route,
  ShieldCheck,
  Stethoscope,
  Terminal,
  Wrench,
} from "lucide-react"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/agent", label: "Diagnose", icon: Stethoscope },
  { href: "/agent/history", label: "History", icon: History },
  { href: "/agent/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/agent/tools", label: "Tools", icon: Wrench },
  { href: "/scenarios", label: "Scenarios", icon: Route },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/operations", label: "Operations", icon: ServerCog },
  { href: "/contracts", label: "API Contracts", icon: FileText },
]

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <aside
      className="hidden md:flex md:w-64 lg:w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
      aria-label="Main navigation"
    >
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-sidebar-border">
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Terminal className="size-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-tight">SmartSRE</span>
          <span className="text-xs text-muted-foreground leading-tight">SRE Copilot</span>
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
                    "group flex items-center gap-3 rounded-md px-3 py-2 transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                  )}
                >
                  <Icon
                    className={cn(
                      "size-4 shrink-0 transition-colors",
                      active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                    )}
                  />
                  <span className="text-sm font-medium">{item.label}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
