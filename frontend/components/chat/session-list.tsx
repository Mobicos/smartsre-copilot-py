"use client"

import { useEffect, useState } from "react"
import { Plus, MessageSquare, Trash2 } from "lucide-react"
import {
  listSessions,
  createSession,
  deleteSession,
  subscribe,
} from "@/lib/sessions-store"
import type { ChatSession } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function SessionList({
  activeId,
  onSelect,
}: {
  activeId?: string
  onSelect: (id: string) => void
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([])

  useEffect(() => {
    setSessions(listSessions())
    return subscribe(() => setSessions(listSessions()))
  }, [])

  const newSession = () => {
    const s = createSession("新对话")
    onSelect(s.id)
  }

  return (
    <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-border bg-card/40">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-3">
        <span className="text-sm font-medium">聊过的话题</span>
        <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={newSession}>
          <Plus className="size-3.5" /> 新开一个
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        {sessions.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 py-8 text-center">
            <MessageSquare className="size-6 text-muted-foreground/60" />
            <p className="text-xs text-muted-foreground text-pretty px-4">
              聊过的话题会留在这里，方便你回头翻
            </p>
            <Button size="sm" variant="ghost" onClick={newSession} className="text-xs h-7">
              开始第一次对话
            </Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-1">
            {sessions.map((s) => (
              <li key={s.id}>
                <div
                  className={cn(
                    "group flex items-center gap-2 rounded-md px-2 py-2 text-sm cursor-pointer transition-colors",
                    activeId === s.id
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent/50",
                  )}
                  onClick={() => onSelect(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelect(s.id)
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm">{s.title}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {s.messages.length === 0 ? "还没说话" : `${s.messages.length} 条消息`}
                    </p>
                  </div>
                  <button
                    aria-label={`删除会话 ${s.title}`}
                    className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteSession(s.id)
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
