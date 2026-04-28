"use client"

import { Bot, User, AlertTriangle, Copy, BookText } from "lucide-react"
import { useState } from "react"
import { Markdown } from "@/components/markdown"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/lib/types"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {}
  }

  return (
    <div
      className={cn("flex gap-3 px-2 sm:px-4", isUser ? "justify-end" : "justify-start")}
      aria-live={message.streaming ? "polite" : undefined}
    >
      {!isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Bot className="size-4" />
        </div>
      )}
      <div className={cn("flex flex-col gap-1.5 max-w-[85%] md:max-w-[75%]", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-lg border px-3.5 py-2.5 text-sm shadow-sm",
            isUser
              ? "border-primary/30 bg-primary text-primary-foreground"
              : "border-border bg-card text-card-foreground",
            message.error && "border-destructive/60",
          )}
        >
          {message.error ? (
            <div className="flex items-start gap-2 text-destructive">
              <AlertTriangle className="size-4 mt-0.5 shrink-0" />
              <p className="text-sm">{message.error}</p>
            </div>
          ) : isUser ? (
            <p className="whitespace-pre-wrap break-words text-pretty">{message.content}</p>
          ) : (
            <>
              <Markdown content={message.content || (message.streaming ? "·" : "")} />
              {message.streaming && (
                <span
                  aria-hidden
                  className="ml-1 inline-block h-3 w-1.5 -translate-y-px animate-pulse-dot bg-primary align-middle"
                />
              )}
            </>
          )}
        </div>

        {!isUser && message.sources && message.sources.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger asChild>
              <button className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                <BookText className="size-3.5" />
                它翻过这 {message.sources.length} 份资料
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-1.5 w-full">
              <ol className="space-y-1.5">
                {message.sources.map((s, i) => (
                  <li
                    key={i}
                    className="rounded-md border border-border bg-card p-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">
                        {s.title || s.source || `来源 ${i + 1}`}
                      </span>
                      {typeof s.score === "number" && (
                        <span className="text-muted-foreground font-mono">
                          {s.score.toFixed(3)}
                        </span>
                      )}
                    </div>
                    {s.snippet && (
                      <p className="mt-1 line-clamp-3 text-muted-foreground leading-relaxed">
                        {s.snippet}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </CollapsibleContent>
          </Collapsible>
        )}

        {!isUser && !message.streaming && message.content && (
          <Button
            variant="ghost"
            size="sm"
            onClick={copy}
            className="h-7 self-start px-2 text-xs text-muted-foreground"
          >
            <Copy className="size-3.5" />
            {copied ? "已复制" : "复制"}
          </Button>
        )}
      </div>
      {isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <User className="size-4" />
        </div>
      )}
    </div>
  )
}
