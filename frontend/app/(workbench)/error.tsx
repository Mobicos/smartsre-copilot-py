"use client"

import { AppErrorFallback } from "@/components/app-error-fallback"

export default function WorkbenchError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <AppErrorFallback
      title="Workbench error"
      description="A workbench panel failed to render. The rest of the app can keep going."
      homeHref="/chat"
      homeLabel="Back to chat"
      error={error}
      reset={reset}
    />
  )
}
