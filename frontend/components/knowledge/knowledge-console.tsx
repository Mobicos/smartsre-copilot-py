"use client"

import { useCallback, useRef, useState } from "react"
import { CheckCircle2, FileText, FileUp, Loader2, Trash2, UploadCloud, XCircle } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import type { IndexingTask } from "@/lib/types"
import { cn } from "@/lib/utils"

const ACCEPT = ".txt,.md,.markdown"
const MAX_BYTES = 10 * 1024 * 1024

const STATUS_LABEL: Record<IndexingTask["status"], string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Indexed",
  failed_permanently: "Failed",
  running: "Uploading",
  succeeded: "Indexed",
  failed: "Failed",
}

function toTaskStatus(status: unknown): IndexingTask["status"] {
  if (status === "queued" || status === "processing" || status === "completed") return status
  if (status === "failed_permanently") return "failed_permanently"
  return "failed"
}

function isTerminal(status: IndexingTask["status"]) {
  return status === "completed" || status === "succeeded" || status === "failed" || status === "failed_permanently"
}

function isSuccess(status: IndexingTask["status"]) {
  return status === "completed" || status === "succeeded"
}

function isFailure(status: IndexingTask["status"]) {
  return status === "failed" || status === "failed_permanently"
}

export function KnowledgeConsole() {
  const [tasks, setTasks] = useState<IndexingTask[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const pollIndexTask = useCallback(async (localId: string, taskId: string) => {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, attempt < 3 ? 1000 : 2500))
      const res = await fetch(`/api/index-tasks/${encodeURIComponent(taskId)}`, {
        cache: "no-store",
      })
      const json = (await res.json()) as Record<string, unknown>
      if (!res.ok) {
        setTasks((items) =>
          items.map((item) =>
            item.id === localId
              ? {
                  ...item,
                  status: "failed",
                  message: typeof json.error === "string" ? json.error : `HTTP ${res.status}`,
                  finishedAt: Date.now(),
                }
              : item,
          ),
        )
        return
      }

      const status = toTaskStatus(json.status)
      setTasks((items) =>
        items.map((item) =>
          item.id === localId
            ? {
                ...item,
                status,
                message: typeof json.error_message === "string" ? json.error_message : undefined,
                finishedAt: isTerminal(status) ? Date.now() : item.finishedAt,
              }
            : item,
        ),
      )
      if (isTerminal(status)) return
    }
  }, [])

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files)
      for (const file of list) {
        if (!/\.(txt|md|markdown)$/i.test(file.name)) {
          toast.error(`${file.name}: only .txt and .md files are supported`)
          continue
        }
        if (file.size > MAX_BYTES) {
          toast.error(`${file.name}: file size must be 10MB or less`)
          continue
        }

        const id = crypto.randomUUID()
        const task: IndexingTask = {
          id,
          filename: file.name,
          size: file.size,
          status: "running",
          startedAt: Date.now(),
        }
        setTasks((items) => [task, ...items])

        try {
          const formData = new FormData()
          formData.append("file", file)
          const res = await fetch("/api/upload", { method: "POST", body: formData })
          const json = (await res.json()) as Record<string, unknown>
          if (!res.ok) {
            setTasks((items) =>
              items.map((item) =>
                item.id === id
                  ? {
                      ...item,
                      status: "failed",
                      message:
                        typeof json.error === "string"
                          ? json.error
                          : typeof json.detail === "string"
                            ? json.detail
                            : `HTTP ${res.status}`,
                      finishedAt: Date.now(),
                    }
                  : item,
              ),
            )
            continue
          }

          const taskId = typeof json.taskId === "string" ? json.taskId : undefined
          const status = toTaskStatus(json.status ?? "queued")
          setTasks((items) =>
            items.map((item) =>
              item.id === id
                ? {
                    ...item,
                    status,
                    message: typeof json.message === "string" ? json.message : undefined,
                    finishedAt: isTerminal(status) ? Date.now() : undefined,
                  }
                : item,
            ),
          )
          if (taskId) void pollIndexTask(id, taskId)
          toast.success(`${file.name}: upload accepted`)
        } catch (err) {
          setTasks((items) =>
            items.map((item) =>
              item.id === id
                ? {
                    ...item,
                    status: "failed",
                    message: (err as Error).message ?? "Upload failed",
                    finishedAt: Date.now(),
                  }
                : item,
            ),
          )
          toast.error(`${file.name}: upload failed`)
        }
      }
    },
    [pollIndexTask],
  )

  const onDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault()
    setDragOver(false)
    if (event.dataTransfer.files?.length) upload(event.dataTransfer.files)
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6 space-y-6">
        <div
          role="button"
          tabIndex={0}
          aria-label="Upload knowledge files"
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click()
          }}
          onDragOver={(event) => {
            event.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed bg-card p-10 text-center transition-colors",
            dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
          )}
        >
          <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <UploadCloud className="size-6" />
          </div>
          <div className="max-w-sm">
            <p className="text-sm font-medium">Upload operational knowledge</p>
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
              Drop Markdown or text runbooks here. Files are uploaded to FastAPI and tracked until
              the backend indexing task completes.
            </p>
          </div>
          <Button type="button" size="sm" variant="outline" className="pointer-events-none">
            <FileUp className="size-4" /> Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(event) => {
              if (event.target.files?.length) upload(event.target.files)
              event.target.value = ""
            }}
          />
        </div>

        <section aria-label="Indexing tasks">
          <header className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-medium text-muted-foreground">Indexing tasks</h2>
            {tasks.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-muted-foreground"
                onClick={() => setTasks([])}
              >
                <Trash2 className="size-3.5" /> Clear
              </Button>
            )}
          </header>
          {tasks.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FileText className="size-5" />
                </EmptyMedia>
                <EmptyTitle>No uploads yet</EmptyTitle>
                <EmptyDescription>
                  Upload a runbook to make it searchable by the SRE copilot.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="space-y-2">
              {tasks.map((task) => {
                const Icon = isSuccess(task.status) ? CheckCircle2 : isFailure(task.status) ? XCircle : Loader2
                const tone = isSuccess(task.status)
                  ? "text-success"
                  : isFailure(task.status)
                    ? "text-destructive"
                    : "text-primary"
                return (
                  <li
                    key={task.id}
                    className={cn(
                      "flex items-start gap-3 rounded-lg border bg-card p-3",
                      isFailure(task.status) && "border-destructive/40",
                      isSuccess(task.status) && "border-success/30",
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-5 mt-0.5 shrink-0",
                        tone,
                        !isTerminal(task.status) && "animate-spin",
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">{task.filename}</span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          {(task.size / 1024).toFixed(1)} KB
                        </span>
                        <span
                          className={cn(
                            "ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium",
                            isSuccess(task.status) && "bg-success/10 text-success",
                            isFailure(task.status) && "bg-destructive/10 text-destructive",
                            (task.status === "running" || task.status === "processing") &&
                              "bg-primary/10 text-primary",
                            task.status === "queued" && "bg-muted text-muted-foreground",
                          )}
                        >
                          {STATUS_LABEL[task.status]}
                        </span>
                      </div>
                      {task.message && !isSuccess(task.status) && (
                        <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                          {task.message}
                        </p>
                      )}
                      {isSuccess(task.status) && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Indexed and ready for retrieval.
                        </p>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
