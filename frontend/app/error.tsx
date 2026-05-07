"use client"

import { AppErrorFallback } from "@/components/app-error-fallback"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <AppErrorFallback
      title="Application error"
      description="The app hit a rendering problem outside the workbench."
      homeHref="/chat"
      homeLabel="Go to chat"
      error={error}
      reset={reset}
    />
  )
}
