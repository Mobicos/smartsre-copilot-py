"use client"

import { CheckCircle2, Circle, CircleDashed, Loader2, XCircle, Wrench, ChevronRight } from "lucide-react"
import type { AiopsStep } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

const ICON: Record<AiopsStep["status"], React.ComponentType<{ className?: string }>> = {
  pending: Circle,
  running: Loader2,
  succeeded: CheckCircle2,
  failed: XCircle,
  skipped: CircleDashed,
}

const TONE: Record<AiopsStep["status"], string> = {
  pending: "text-muted-foreground",
  running: "text-primary animate-spin",
  succeeded: "text-success",
  failed: "text-destructive",
  skipped: "text-muted-foreground",
}

const LABEL: Record<AiopsStep["status"], string> = {
  pending: "等会儿做",
  running: "正在做",
  succeeded: "做完了",
  failed: "没做成",
  skipped: "跳过了",
}

export function PlanTimeline({ steps }: { steps: AiopsStep[] }) {
  if (steps.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        它正在想该怎么查，稍等一下…
      </div>
    )
  }

  return (
    <ol className="relative">
      {steps.map((s, i) => {
        const Icon = ICON[s.status]
        return (
          <li key={s.id} className="relative pl-9 pb-4 last:pb-0">
            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "absolute left-3 top-8 bottom-0 w-px",
                  s.status === "succeeded" ? "bg-success/50" : "bg-border",
                )}
              />
            )}
            <span
              aria-hidden
              className={cn(
                "absolute left-0 top-1.5 flex size-6 items-center justify-center rounded-full border bg-card",
                s.status === "running" && "border-primary",
                s.status === "succeeded" && "border-success",
                s.status === "failed" && "border-destructive",
                s.status === "pending" && "border-border",
              )}
            >
              <Icon className={cn("size-3.5", TONE[s.status])} />
            </span>
            <div
              className={cn(
                "rounded-lg border bg-card px-4 py-3 transition-colors",
                s.status === "running" && "border-primary/50 shadow-sm",
                s.status === "failed" && "border-destructive/50",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium leading-snug text-pretty">{s.title}</p>
                  {s.description && (
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                      {s.description}
                    </p>
                  )}
                </div>
                <span
                  className={cn(
                    "text-[11px] font-mono shrink-0 rounded px-1.5 py-0.5",
                    s.status === "running" && "bg-primary/10 text-primary",
                    s.status === "succeeded" && "bg-success/10 text-success",
                    s.status === "failed" && "bg-destructive/10 text-destructive",
                    s.status === "pending" && "bg-muted text-muted-foreground",
                    s.status === "skipped" && "bg-muted text-muted-foreground",
                  )}
                >
                  {LABEL[s.status]}
                </span>
              </div>

              {(s.toolCalls.length > 0 || s.output) && (
                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <button className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
                      <ChevronRight className="size-3 transition-transform data-[state=open]:rotate-90" />
                      看看它做了什么 {s.toolCalls.length > 0 && `· 用了 ${s.toolCalls.length} 个工具`}
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 space-y-1.5">
                    {s.toolCalls.map((t) => (
                      <div
                        key={t.id}
                        className="rounded-md border border-border bg-muted/40 p-2 text-xs"
                      >
                        <div className="flex items-center gap-1.5 font-mono">
                          <Wrench className="size-3 text-primary" />
                          <span className="font-medium">{t.name}</span>
                          <span
                            className={cn(
                              "ml-auto rounded px-1.5 py-0.5 text-[10px]",
                              t.status === "running" && "bg-primary/10 text-primary",
                              t.status === "succeeded" && "bg-success/10 text-success",
                              t.status === "failed" && "bg-destructive/10 text-destructive",
                            )}
                          >
                            {t.status}
                          </span>
                        </div>
                        {t.args !== undefined && (
                          <pre className="mt-1.5 max-h-32 overflow-auto rounded bg-background p-1.5 text-[11px] leading-snug font-mono scrollbar-thin">
                            {typeof t.args === "string" ? t.args : JSON.stringify(t.args, null, 2)}
                          </pre>
                        )}
                        {t.result !== undefined && (
                          <pre className="mt-1.5 max-h-40 overflow-auto rounded bg-background p-1.5 text-[11px] leading-snug font-mono scrollbar-thin">
                            {typeof t.result === "string"
                              ? t.result
                              : JSON.stringify(t.result, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                    {s.output && (
                      <pre className="rounded-md border border-border bg-muted/40 p-2 text-xs whitespace-pre-wrap font-mono">
                        {s.output}
                      </pre>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
