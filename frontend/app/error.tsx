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
      title="应用错误"
      description="应用在工作台外部遇到了渲染问题。"
      homeHref="/chat"
      homeLabel="返回对话"
      error={error}
      reset={reset}
    />
  )
}
