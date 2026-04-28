"use client"

import { useReducer, useState } from "react"
import { Stethoscope, Play, Square, RotateCcw, FileText, AlertTriangle, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { Markdown } from "@/components/markdown"
import { PlanTimeline } from "./plan-timeline"
import { useEventStream } from "@/lib/use-event-stream"
import { tryParseJSON } from "@/lib/sse"
import {
  diagnoseReducer,
  initialRun,
  interpretEvent,
} from "@/lib/diagnose-reducer"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

const PRESETS = [
  "API 延迟从 80ms 突然涨到了 800ms",
  "有几个 Pod 一直在反复重启",
  "数据库连接池又被打满了",
]

const PHASE_LABEL: Record<string, string> = {
  idle: "等你描述",
  planning: "正在想怎么查",
  executing: "正在排查",
  replanning: "调整思路中",
  reporting: "整理结论中",
  done: "查完了",
  error: "中断了",
}

export function DiagnoseConsole() {
  const [query, setQuery] = useState("")
  const [run, dispatch] = useReducer(diagnoseReducer, initialRun)
  const { start, abort } = useEventStream()
  const [running, setRunning] = useState(false)

  const launch = async (text?: string) => {
    const q = (text ?? query).trim()
    if (!q) return
    dispatch({ type: "reset", query: q })
    setRunning(true)

    try {
      await start(
        "/api/aiops",
        { query: q, question: q, problem: q },
        {
          onEvent: (event, data) => {
            const parsed = tryParseJSON(data)
            const actions = interpretEvent(event, parsed)
            for (const a of actions) dispatch(a)
          },
          onError: (err) => {
            dispatch({ type: "error", message: (err as Error)?.message ?? "诊断中断" })
            toast.error("诊断流程失败，请检查后端服务")
          },
          onDone: () => dispatch({ type: "done" }),
        },
      )
    } finally {
      setRunning(false)
    }
  }

  const stop = () => {
    abort()
    setRunning(false)
    dispatch({ type: "error", message: "已被用户中断" })
  }

  const reset = () => {
    abort()
    setRunning(false)
    dispatch({ type: "reset", query: "" })
    setQuery("")
  }

  const phaseClass =
    run.phase === "done"
      ? "bg-success/15 text-success border-success/30"
      : run.phase === "error"
        ? "bg-destructive/15 text-destructive border-destructive/30"
        : run.phase === "idle"
          ? "bg-muted text-muted-foreground border-border"
          : "bg-primary/15 text-primary border-primary/30"

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Launcher */}
      <div className="border-b border-border bg-card/40 px-4 py-4 md:px-6">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-start gap-3">
            <div className="hidden sm:flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Stethoscope className="size-5" />
            </div>
            <div className="flex-1 min-w-0">
              <Textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={running}
                placeholder="把现象描述给它。比如『下单接口从 10:20 开始大量报错，订单服务的 P99 也涨上来了』。它会先告诉你打算怎么查，再一步步动手。"
                className="min-h-[88px] resize-none bg-background"
                aria-label="故障描述"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {PRESETS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setQuery(p)}
                    disabled={running}
                    className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground disabled:opacity-50"
                  >
                    <Sparkles className="mr-1 inline size-3 text-primary" />
                    {p}
                  </button>
                ))}
                <div className="ml-auto flex gap-2">
                  {running ? (
                    <Button variant="destructive" onClick={stop}>
                      <Square className="size-4 fill-current" /> 让它停下
                    </Button>
                  ) : (
                    <>
                      <Button variant="outline" onClick={reset} disabled={run.phase === "idle"}>
                        <RotateCcw className="size-4" /> 重新开始
                      </Button>
                      <Button onClick={() => launch()} disabled={!query.trim()}>
                        <Play className="size-4" /> 让它去查
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
          {run.phase === "idle" ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Stethoscope className="size-5" />
                </EmptyMedia>
                <EmptyTitle>把现场交给它</EmptyTitle>
                <EmptyDescription className="max-w-md text-pretty">
                  描述发生了什么——它会先把排查思路摆出来给你看，再一步步动手。
                  你能看到它在查什么、用了什么工具、得到了什么。最后给你一份能直接复制进复盘文档的结论。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="flex flex-col gap-4">
              {/* Status header */}
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-4">
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-muted-foreground">
                    你交给它的问题
                  </p>
                  <p className="mt-0.5 text-sm font-medium text-pretty">{run.query}</p>
                </div>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                    phaseClass,
                  )}
                >
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      run.phase === "done"
                        ? "bg-success"
                        : run.phase === "error"
                          ? "bg-destructive"
                          : "bg-primary animate-pulse-dot",
                    )}
                  />
                  {PHASE_LABEL[run.phase] ?? run.phase}
                </span>
              </div>

              {run.error && (
                <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                  <AlertTriangle className="size-4 mt-0.5 shrink-0" />
                  <span>{run.error}</span>
                </div>
              )}

              {/* Plan + steps */}
              <section aria-label="排查过程">
                <h2 className="mb-2 text-xs font-medium text-muted-foreground">
                  它正在做这些事
                </h2>
                <PlanTimeline steps={run.steps} />
              </section>

              {/* Final report */}
              {run.report && (
                <section
                  aria-label="诊断结论"
                  className="rounded-lg border border-border bg-card p-5"
                >
                  <header className="mb-3 flex items-center gap-2">
                    <FileText className="size-4 text-primary" />
                    <h2 className="text-sm font-semibold">它给出的结论</h2>
                  </header>
                  <Markdown content={run.report} />
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
