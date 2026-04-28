"use client"

import { useEffect, useRef, useState } from "react"
import { ArrowUp, Square, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export interface ComposerProps {
  onSubmit: (text: string, opts: { stream: boolean }) => void
  onStop?: () => void
  isRunning?: boolean
  placeholder?: string
}

export function Composer({ onSubmit, onStop, isRunning, placeholder }: ComposerProps) {
  const [value, setValue] = useState("")
  const [stream, setStream] = useState(true)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [value])

  const submit = () => {
    const text = value.trim()
    if (!text || isRunning) return
    onSubmit(text, { stream })
    setValue("")
  }

  return (
    <div className="border-t border-border bg-background/95 px-3 py-3 backdrop-blur md:px-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-2">
        <div
          className={cn(
            "flex items-end gap-2 rounded-xl border border-border bg-card p-2 shadow-sm transition-shadow",
            "focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-ring/30",
          )}
        >
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit()
              }
            }}
            placeholder={placeholder ?? "把问题写在这里，按 Enter 发送"}
            className="min-h-[44px] max-h-[220px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed outline-none placeholder:text-muted-foreground"
            aria-label="提问输入框"
            rows={1}
          />
          {isRunning ? (
            <Button
              type="button"
              variant="destructive"
              size="icon"
              onClick={onStop}
              aria-label="停止生成"
              className="size-9 shrink-0"
            >
              <Square className="size-4 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              size="icon"
              onClick={submit}
              disabled={!value.trim()}
              aria-label="发送"
              className="size-9 shrink-0"
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
        <div className="flex items-center justify-between gap-2 px-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Switch
              id="stream-toggle"
              checked={stream}
              onCheckedChange={setStream}
              aria-label="切换流式响应"
            />
            <Label htmlFor="stream-toggle" className="flex items-center gap-1 text-xs">
              <Zap className="size-3.5" />
              一边想一边说
            </Label>
          </div>
          <span>Enter 发送 · Shift + Enter 换行</span>
        </div>
      </div>
    </div>
  )
}
