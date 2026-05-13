"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Bot, Sparkles } from "lucide-react"
import { MessageBubble } from "./message-bubble"
import { Composer } from "./composer"
import { SessionList } from "./session-list"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty"
import { Button } from "@/components/ui/button"
import { useEventStream } from "@/lib/use-event-stream"
import { tryParseJSON } from "@/lib/sse"
import type { ChatMessage, ChatSession, ChatSource } from "@/lib/types"
import {
  createSession,
  getSession,
  listSessions,
  setMessages as persistMessages,
  subscribe,
  renameSession,
} from "@/lib/sessions-store"

const SUGGESTIONS = [
  "我们之前是怎么处理 Redis 主从切换的？",
  "线上 Pod 一直在重启，可能是哪些原因？",
  "把这段错误日志解释给我听，我看不太懂",
  "数据库连接池打满了，先做哪几件事？",
]

interface AssistantBuf {
  content: string
  sources: ChatSource[]
}

export function ChatWorkbench() {
  const [activeId, setActiveId] = useState<string | undefined>(undefined)
  const [session, setSession] = useState<ChatSession | undefined>(undefined)
  const { start, abort, isRunning } = useEventStream()
  const [running, setRunning] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // initialize: pick or create a session
  useEffect(() => {
    const all = listSessions()
    if (all.length > 0) setActiveId(all[0].id)
    else setActiveId(createSession("新对话").id)
  }, [])

  useEffect(() => {
    if (!activeId) return
    const refresh = () => setSession(getSession(activeId))
    refresh()
    return subscribe(refresh)
  }, [activeId])

  const messages = useMemo<ChatMessage[]>(() => session?.messages ?? [], [session])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
  }, [messages.length, running])

  const persist = (next: ChatMessage[]) => {
    if (!activeId) return
    persistMessages(activeId, next)
  }

  const submit = async (text: string, opts: { stream: boolean }) => {
    if (!activeId) return
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    }
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      createdAt: Date.now(),
      streaming: true,
    }
    const next = [...messages, userMsg, assistantMsg]
    persist(next)

    // auto title on first user message
    const current = getSession(activeId)
    if (current && current.messages.length === 0) {
      renameSession(activeId, text.slice(0, 24))
    }

    setRunning(true)

    if (opts.stream) {
      const buf: AssistantBuf = { content: "", sources: [] }
      try {
        await start(
          "/api/chat/stream",
          { question: text, query: text, session_id: activeId },
          {
            onEvent: (event, data) => {
              const parsed = tryParseJSON(data)
              if (event === "error") {
                const msg =
                  typeof parsed === "object" && parsed && "error" in parsed
                    ? String((parsed as { error: unknown }).error)
                    : String(parsed)
                applyAssistant(activeId, assistantMsg.id, {
                  content: buf.content,
                  sources: buf.sources,
                  streaming: false,
                  error: msg,
                })
                return
              }
              // Process content chunks
              if (typeof parsed === "object" && parsed !== null) {
                const p = parsed as Record<string, unknown>
                if (p.type === "content" && typeof p.data === "string") {
                  buf.content += p.data
                } else if (p.type === "done" && p.data && typeof p.data === "object") {
                  const done = p.data as Record<string, unknown>
                  if (typeof done.answer === "string") buf.content = done.answer
                } else if (p.type === "error") {
                  applyAssistant(activeId, assistantMsg.id, {
                    content: buf.content,
                    sources: buf.sources,
                    streaming: false,
                    error: typeof p.data === "string" ? p.data : "流式传输错误",
                  })
                  return
                }
                if (Array.isArray(p.sources)) {
                  buf.sources = p.sources as ChatSource[]
                }
              }
              applyAssistant(activeId, assistantMsg.id, {
                content: buf.content,
                sources: buf.sources,
                streaming: true,
              })
            },
            onError: (err) => {
              applyAssistant(activeId, assistantMsg.id, {
                content: buf.content,
                sources: buf.sources,
                streaming: false,
                error: (err as Error)?.message ?? "请求失败",
              })
              toast.error("流式请求失败，请检查后端是否已启动")
            },
            onDone: () => {
              applyAssistant(activeId, assistantMsg.id, {
                content: buf.content,
                sources: buf.sources,
                streaming: false,
              })
            },
          },
        )
      } finally {
        setRunning(false)
      }
    } else {
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question: text, query: text, session_id: activeId }),
        })
        const json = (await res.json()) as Record<string, unknown>
        const content =
          (typeof json.answer === "string" && json.answer) ||
          (typeof json.content === "string" && json.content) ||
          (typeof json.text === "string" && json.text) ||
          (typeof json.response === "string" && json.response) ||
          ""
        const sources = Array.isArray(json.sources) ? (json.sources as ChatSource[]) : []
        applyAssistant(activeId, assistantMsg.id, {
          content: content || "（后端无返回内容）",
          sources,
          streaming: false,
          error: !res.ok ? `HTTP ${res.status}` : undefined,
        })
      } catch (err) {
        applyAssistant(activeId, assistantMsg.id, {
          content: "",
          sources: [],
          streaming: false,
          error: (err as Error).message ?? "请求失败",
        })
      } finally {
        setRunning(false)
      }
    }
  }

  function applyAssistant(
    sessionId: string,
    msgId: string,
    patch: Partial<ChatMessage>,
  ) {
    const s = getSession(sessionId)
    if (!s) return
    const next = s.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m))
    persistMessages(sessionId, next)
  }

  const stop = () => {
    abort()
    setRunning(false)
    if (!activeId) return
    const s = getSession(activeId)
    if (!s) return
    const next = s.messages.map((m) =>
      m.role === "assistant" && m.streaming ? { ...m, streaming: false } : m,
    )
    persistMessages(activeId, next)
  }

  void isRunning

  return (
    <div className="flex h-full min-h-0">
      <SessionList activeId={activeId} onSelect={setActiveId} />
      <section className="flex flex-1 min-w-0 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto flex max-w-3xl flex-col gap-4 py-6">
            {messages.length === 0 ? (
              <Empty className="mx-2 sm:mx-4">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Bot className="size-5" />
                  </EmptyMedia>
                  <EmptyTitle>今天遇到什么了？</EmptyTitle>
                  <EmptyDescription>
                    把问题写下来。它会先翻阅你们上传的运维资料，再给出答案，并附上看过的原文。
                  </EmptyDescription>
                </EmptyHeader>
                <EmptyContent>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {SUGGESTIONS.map((s) => (
                      <Button
                        key={s}
                        variant="outline"
                        className="h-auto justify-start whitespace-normal text-left text-sm"
                        onClick={() => submit(s, { stream: true })}
                      >
                        <Sparkles className="size-3.5 shrink-0 text-primary" />
                        <span className="text-pretty">{s}</span>
                      </Button>
                    ))}
                  </div>
                </EmptyContent>
              </Empty>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
          </div>
        </div>
        <Composer onSubmit={submit} onStop={stop} isRunning={running} />
      </section>
    </div>
  )
}
