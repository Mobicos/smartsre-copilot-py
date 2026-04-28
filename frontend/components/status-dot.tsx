import { cn } from "@/lib/utils"

type Tone = "ok" | "warn" | "error" | "muted"

const toneClass: Record<Tone, string> = {
  ok: "bg-success",
  warn: "bg-warning",
  error: "bg-destructive",
  muted: "bg-muted-foreground/40",
}

export function StatusDot({
  tone = "muted",
  pulse = false,
  className,
  label,
}: {
  tone?: Tone
  pulse?: boolean
  className?: string
  label?: string
}) {
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      className={cn(
        "inline-block size-2 rounded-full",
        toneClass[tone],
        pulse && "animate-pulse-dot",
        className,
      )}
    />
  )
}
