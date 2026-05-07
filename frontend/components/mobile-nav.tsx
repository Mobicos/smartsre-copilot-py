"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  BookOpen,
  FileText,
  History,
  Menu,
  MessageSquare,
  Route,
  ServerCog,
  ShieldCheck,
  Stethoscope,
  Terminal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/agent", label: "Diagnose", icon: Stethoscope },
  { href: "/agent/history", label: "History", icon: History },
  { href: "/agent/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/scenarios", label: "Scenarios", icon: Route },
  { href: "/operations", label: "Operations", icon: ServerCog },
  { href: "/contracts", label: "API Contracts", icon: FileText },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
] as const

export function MobileNav() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation">
          <Menu className="size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="flex items-center gap-2 text-left">
            <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Terminal className="size-4" />
            </span>
            SmartSRE Copilot
          </SheetTitle>
        </SheetHeader>
        <nav className="p-2">
          <ul className="flex flex-col gap-1">
            {NAV.map((item) => {
              const active = pathname === item.href || pathname?.startsWith(`${item.href}/`)
              const Icon = item.icon
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                      active ? "bg-accent text-accent-foreground" : "hover:bg-accent/60",
                    )}
                  >
                    <Icon className="size-4 text-muted-foreground" />
                    {item.label}
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </SheetContent>
    </Sheet>
  )
}
